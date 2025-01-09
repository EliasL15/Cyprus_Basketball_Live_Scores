# app.py
import asyncio
from flask import Flask, render_template, jsonify
from flask_caching import Cache
from playwright.async_api import async_playwright
import re
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import atexit
import logging

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
scheduler = AsyncIOScheduler()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

playwright_instance = None
browser = None
page = None

async def initialize_playwright():
    global playwright_instance, browser, page
    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto("https://www.cbf.basketball/")
    await page.wait_for_selector('.mbt-game-scroller-v2-game')

async def scrape_dynamic_content_async():
    logging.info("Starting scrape_dynamic_content_async")
    live_games = []
    all_games = []
    current_month = datetime.now().strftime('%m')

    try:
        # Refresh the page to get the latest content
        await page.reload()
        await page.wait_for_selector('.mbt-game-scroller-v2-game', timeout=30000)  # 30 seconds

        # Extract content of all game elements and filter live games
        games = await page.query_selector_all('.mbt-game-scroller-v2-game')
        logging.info(f"Found {len(games)} games on the page.")

        for game in games:
            try:
                team_a_name = (await (await game.query_selector('.mbt-game-scroller-v2-teams-team-a-name')).inner_text()).strip()
                team_a_score = (await (await game.query_selector('.mbt-game-scroller-v2-teams-team-a-score')).inner_text()).strip()
                team_b_name = (await (await game.query_selector('.mbt-game-scroller-v2-teams-team-b-name')).inner_text()).strip()
                team_b_score = (await (await game.query_selector('.mbt-game-scroller-v2-teams-team-b-score')).inner_text()).strip()

                # Extract URL from the href attribute
                href = await game.get_attribute('href') or ""
                match = re.search(r"window\.open\('([^']+)'", href)
                game_url = match.group(1) if match else f"https://www.cbf.basketball/{href}"

                # Extract quarter, time left, date, and league name
                quarter_elem = await game.query_selector('.mbt-game-scroller-v2-game-info-time')
                quarter = (await quarter_elem.inner_text()).strip() if quarter_elem else "N/A"

                time_left = (await quarter_elem.evaluate('(element) => element.nextSibling.textContent')).strip() if quarter_elem else "N/A"

                date_elem = await game.query_selector('.mbt-game-scroller-v2-game-info-date')
                game_date = (await date_elem.inner_text()).strip() if date_elem else "N/A"

                league_elem = await game.query_selector('.mbt-game-scroller-v2-league-name')
                league_name = (await league_elem.inner_text()).strip() if league_elem else "N/A"

                game_data = {
                    'team_a_name': team_a_name,
                    'team_a_score': team_a_score,
                    'team_b_name': team_b_name,
                    'team_b_score': team_b_score,
                    'url': game_url,
                    'quarter': quarter,
                    'time_left': time_left,
                    'date': game_date,
                    'league_name': league_name
                }

                if game_date.startswith(current_month):
                    all_games.append(game_data)

                classes = await game.get_attribute('class')
                if 'mbt-game-scroller-v2-live' in classes:
                    live_games.append(game_data)

            except Exception as e:
                logging.warning(f"Error processing a game element: {e}", exc_info=True)
                continue  # Skip to the next game

        # Sort all games by date and time_left attribute
        all_games.sort(key=lambda x: (x['date'], x['time_left']), reverse=True)

        logging.info(f"Scraped {len(live_games)} live games and {len(all_games)} total games.")
        return live_games, all_games

    except Exception as e:
        logging.error(f"Error during scraping: {e}", exc_info=True)
        return [], []

async def scrape_and_cache_async():
    live_games, all_games = await scrape_dynamic_content_async()
    if live_games:
        cache.set('live_games', live_games, timeout=120)
        logging.info(f"Cached {len(live_games)} live games.")
    else:
        logging.warning("No live games to cache.")

    if all_games:
        cache.set('all_games', all_games, timeout=120)
        logging.info(f"Cached {len(all_games)} total games.")
    else:
        logging.warning("No games to cache.")

async def close_playwright():
    global browser, playwright_instance
    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()
    logging.info("Playwright closed.")

def shutdown():
    logging.info("Shutting down...")
    scheduler.shutdown()
    asyncio.run(close_playwright())

atexit.register(shutdown)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/live-scores')
def live_scores():
    live_games = cache.get('live_games') or []
    return jsonify(live_games)

@app.route('/api/all-games')
def all_games_route():
    all_games = cache.get('all_games') or []
    return jsonify(all_games)

if __name__ == '__main__':
    # Initialize Playwright and start the scheduler
    asyncio.run(initialize_playwright())
    scheduler.add_job(scrape_and_cache_async, 'interval', minutes=2, next_run_time=datetime.now())
    scheduler.start()

    # Perform initial scrape
    asyncio.run(scrape_and_cache_async())

    # Run Flask with an asynchronous server like Uvicorn
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
