import os
from flask import Flask, render_template, jsonify
from flask_caching import Cache
from playwright.sync_api import sync_playwright
import re
from datetime import datetime
from flask_apscheduler import APScheduler
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
scheduler = APScheduler()
scheduler.init_app(app)

scraped_data = {}

def install_playwright_deps():
    try:
        import subprocess
        logging.info("Installing Playwright dependencies...")
        subprocess.run(['playwright', 'install', 'chromium'])
        subprocess.run(['playwright', 'install-deps', 'chromium'])
        logging.info("Playwright dependencies installed successfully")
    except Exception as e:
        logging.error(f"Error installing Playwright dependencies: {e}")

def scrape_dynamic_content():
    try:
        live_games = []
        all_games = []
        current_month = datetime.now().strftime('%m')

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logging.info("Navigating to website...")
            page.goto("https://www.cbf.basketball/")
            
            logging.info("Waiting for selector...")
            page.wait_for_selector('.mbt-game-scroller-v2-game')
            games = page.query_selector_all('.mbt-game-scroller-v2-game')
            
            logging.info(f"Found {len(games)} games")
            
            # ... rest of the scraping code remains the same ...

    except Exception as e:
        logging.error(f"Error in scrape_dynamic_content: {e}", exc_info=True)
        return {'live_games': [], 'all_games': []}

def scheduled_scrape():
    global scraped_data
    logging.info("Starting scheduled scrape")
    try:
        new_data = scrape_dynamic_content()
        scraped_data.update(new_data)
        logging.info(f"Scheduled scrape completed. Data: {scraped_data}")
    except Exception as e:
        logging.error(f"Error in scheduled scrape: {e}", exc_info=True)

@app.before_first_request
def init_scheduler():
    logging.info("Initializing scheduler...")
    scheduler.start()
    scheduler.add_job(id='ScrapeJob', func=scheduled_scrape, trigger='interval', minutes=2)
    install_playwright_deps()
    scheduled_scrape()
    logging.info("Scheduler initialized and first scrape completed")

# ... rest of the routes remain the same ...

if __name__ == '__main__':
    port = 5001
    debug = True
    logging.info(f"Starting app on port {port} with debug={debug}")
    app.run(debug=debug, port=port)