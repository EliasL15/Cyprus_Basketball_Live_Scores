from flask import Flask, render_template, jsonify
from flask_caching import Cache
from playwright.sync_api import sync_playwright
import re
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import logging

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
scheduler = BackgroundScheduler()

logging.basicConfig(level=logging.INFO)

# Initialize Playwright and browser at startup
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True)
page = browser.new_page()
page.goto("https://www.cbf.basketball/")
page.wait_for_selector('.mbt-game-scroller-v2-game')

# Ensure browser is closed on exit
def shutdown_browser():
    browser.close()
    playwright.stop()
    scheduler.shutdown()
    logging.info("Browser and scheduler shut down.")

atexit.register(shutdown_browser)

def scrape_dynamic_content():
    live_games = []
    all_games = []
    current_month = datetime.now().strftime('%m')

    try:
        # Refresh the page to get the latest content
        page.reload()
        page.wait_for_selector('.mbt-game-scroller-v2-game', timeout=30000)  # 30 seconds timeout

        # Extract content of all game elements and filter live games
        games = page.query_selector_all('.mbt-game-scroller-v2-game')
        for game in games:
            team_a = game.query_selector('.mbt-game-scroller-v2-teams-team-a-name')
            team_b = game.query_selector('.mbt-game-scroller-v2-teams-team-b-name')
            score_a = game.query_selector('.mbt-game-scroller-v2-teams-team-a-score')
            score_b = game.query_selector('.mbt-game-scroller-v2-teams-team-b-score')
            
            team_a_name = team_a.inner_text() if team_a else "N/A"
            team_a_score = score_a.inner_text() if score_a else "0"
            team_b_name = team_b.inner_text() if team_b else "N/A"
            team_b_score = score_b.inner_text() if score_b else "0"
            
            # Extract URL from the href attribute
            href = game.get_attribute('href') or ""
            match = re.search(r"window\.open\('([^']+)'", href)
            game_url = match.group(1) if match else f"https://www.cbf.basketball/{href}"
            
            # Extract quarter, time left, date, and league name
            quarter_elem = game.query_selector('.mbt-game-scroller-v2-game-info-time')
            quarter = quarter_elem.inner_text().strip() if quarter_elem else "N/A"
            
            time_left = game.evaluate('(element) => element.nextSibling.textContent', quarter_elem).strip() if quarter_elem else "N/A"
            
            date_elem = game.query_selector('.mbt-game-scroller-v2-game-info-date')
            game_date = date_elem.inner_text().strip() if date_elem else "N/A"
            
            league_elem = game.query_selector('.mbt-game-scroller-v2-league-name')
            league_name = league_elem.inner_text().strip() if league_elem else "N/A"
            
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
            
            if 'mbt-game-scroller-v2-live' in game.get_attribute('class'):
                live_games.append(game_data)

        # Sort all games by date and time_left attribute
        all_games.sort(key=lambda x: (x['date'], x['time_left']), reverse=True)

        logging.info(f"Scraped {len(live_games)} live games and {len(all_games)} total games.")
        return live_games, all_games

    except Exception as e:
        logging.error(f"Error during scraping: {e}")
        return [], []

def scrape_and_cache():
    live_games, all_games = scrape_dynamic_content()
    cache.set('live_games', live_games, timeout=120)
    cache.set('all_games', all_games, timeout=120)

# Schedule scraping every 2 minutes
scheduler.add_job(scrape_and_cache, 'interval', minutes=2)
scheduler.start()

# Initial scrape
scrape_and_cache()

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
    app.run(debug=False, port=5001)
