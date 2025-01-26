from flask import Flask, render_template, jsonify
from playwright.sync_api import sync_playwright
import re
from datetime import datetime
import threading
import time
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Global variables to store scraped data and lock for thread safety
scraped_data = None
data_lock = threading.Lock()

def scrape_dynamic_content():
    live_games = []
    all_games = []
    current_month = datetime.now().strftime('%m')

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )

            page = browser.new_page()
            page.goto("https://www.cbf.basketball/")
            
            page.wait_for_selector('.mbt-game-scroller-v2-game')
            games = page.query_selector_all('.mbt-game-scroller-v2-game')
            
            for game in games:
                team_a_name = game.query_selector('.mbt-game-scroller-v2-teams-team-a-name').inner_text()
                team_a_score = game.query_selector('.mbt-game-scroller-v2-teams-team-a-score').inner_text()
                team_b_name = game.query_selector('.mbt-game-scroller-v2-teams-team-b-name').inner_text()
                team_b_score = game.query_selector('.mbt-game-scroller-v2-teams-team-b-score').inner_text()
                
                # Attempt to parse href
                href = game.get_attribute('href')
                match = re.search(r"window\.open\('([^']+)'", href)
                if match:
                    game_url = match.group(1)
                else:
                    game_url = f"https://www.cbf.basketball/{href}"
                
                quarter = game.query_selector('.mbt-game-scroller-v2-game-info-time').inner_text().strip()
                time_left = game.evaluate(
                    '(element) => element.nextSibling?.textContent || ""',
                    game.query_selector('.mbt-game-scroller-v2-game-info-time')
                ).strip()
                
                game_date = game.query_selector('.mbt-game-scroller-v2-game-info-date').inner_text().strip()
                league_name = game.query_selector('.mbt-game-scroller-v2-league-name').inner_text().strip()
                
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

            browser.close()
    except Exception as e:
        logging.error(f"Scraping error: {str(e)}")
    
    return {
        'live_games': live_games,
        'all_games': all_games
    }

def continuous_scraper():
    global scraped_data
    logging.info("Starting continuous scraper")
    while True:
        try:
            new_data = scrape_dynamic_content()
            with data_lock:
                scraped_data = new_data
            logging.info(f"Successfully updated game data: {scraped_data}")
        except Exception as e:
            logging.error(f"Scraping error: {str(e)}")
        time.sleep(30)  # Wait 30 seconds between scrapes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/games')
def get_games():
    """Return the latest scraped data."""
    global scraped_data
    with data_lock:
        if scraped_data is None:
            return jsonify({"error": "Data not available yet"}), 503
        return jsonify(scraped_data)

@app.route('/api/scraper_status')
def scraper_status():
    """Return the status of the scraper."""
    global scraped_data
    with data_lock:
        if scraped_data is None:
            return jsonify({"status": "Scraper not yet initialized"}), 200
        return jsonify({"status": "Scraper running", "data_count": len(scraped_data['all_games'])}), 200

if __name__ == '__main__':
    # Start background scraping thread
    scraper_thread = threading.Thread(target=continuous_scraper, daemon=True)
    scraper_thread.start()
    app.run(debug=True, port=8000)