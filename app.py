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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# Define routes
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

# Scraping function
async def scrape_dynamic_content_async():
    logging.info("Starting scrape_dynamic_content_async")
    live_games = []
    all_games = []
    current_month = datetime.now().strftime('%m')

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://www.cbf.basketball/")
            await page.wait_for_selector('.mbt-game-scroller-v2-game', timeout=30000)

            games = await page.query_selector_all('.mbt-game-scroller-v2-game')
            logging.info(f"Found {len(games)} games on the page.")

            for game in games:
                try:
                    # Extract team names and scores
                    team_a_query = await game.query_selector('.mbt-game-scroller-v2-teams-team-a-name')
                    team_a_name = (await team_a_query.inner_text()).strip() if team_a_query else "N/A"

                    team_a_score_query = await game.query_selector('.mbt-game-scroller-v2-teams-team-a-score')
                    team_a_score = (await team_a_score_query.inner_text()).strip() if team_a_score_query else "0"

                    team_b_query = await game.query_selector('.mbt-game-scroller-v2-teams-team-b-name')
                    team_b_name = (await team_b_query.inner_text()).strip() if team_b_query else "N/A"

                    team_b_score_query = await game.query_selector('.mbt-game-scroller-v2-teams-team-b-score')
                    team_b_score = (await team_b_score_query.inner_text()).strip() if team_b_score_query else "0"

                    # Extract game URL
                    href = await game.get_attribute('href') or ""
                    match = re.search(r"window\.open\('([^']+)'", href)
                    game_url = match.group(1) if match else f"https://www.cbf.basketball/{href}"

                    # Extract game info
                    quarter_elem = await game.query_selector('.mbt-game-scroller-v2-game-info-time')
                    quarter = (await quarter_elem.inner_text()).strip() if quarter_elem else "N/A"

                    time_left = (await quarter_elem.evaluate('(element) => element.nextSibling.textContent')).strip() if quarter_elem else "N/A"

                    date_elem = await game.query_selector('.mbt-game-scroller-v2-game-info-date')
                    game_date = (await date_elem.inner_text()).strip() if date_elem else "N/A"

                    league_elem = await game.query_selector('.mbt-game-scroller-v2-league-name')
                    league_name = (await league_elem.inner_text()).strip() if league_elem else "N/A"

                    # Compile game data
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

                    # Filter games by current month
                    if game_date.startswith(current_month):
                        all_games.append(game_data)

                    # Identify live games
                    classes = await game.get_attribute('class')
                    if 'mbt-game-scroller-v2-live' in classes:
                        live_games.append(game_data)

                except Exception as e:
                    logging.warning(f"Error processing a game element: {e}", exc_info=True)
                    continue  # Skip to the next game

            # Sort all games by date and time_left in descending order
            all_games.sort(key=lambda x: (x['date'], x['time_left']), reverse=True)

            logging.info(f"Scraped {len(live_games)} live games and {len(all_games)} total games.")
            await browser.close()
            return live_games, all_games

    except Exception as e:
        logging.error(f"Error during scraping: {e}", exc_info=True)
        return [], []

# Scheduler job to scrape and cache data
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

# Graceful shutdown handler
async def shutdown():
    logging.info("Shutting down scheduler...")
    scheduler.shutdown()
    logging.info("Scheduler shut down.")

    # No persistent Playwright instances to close since they are handled within the scraping job
    logging.info("Shutdown complete.")

# Register shutdown handler
atexit.register(lambda: asyncio.run(shutdown()))

# Main function to initialize scheduler and start server
async def main():
    # Add scraping job to the scheduler to run every 2 minutes
    scheduler.add_job(scrape_and_cache_async, 'interval', minutes=2, next_run_time=datetime.now())
    scheduler.start()

    # Perform an initial scrape
    await scrape_and_cache_async()

    # Start the Uvicorn server
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=5001, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application stopped manually.")
