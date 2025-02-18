from flask import Flask, render_template, jsonify
import requests
import json
import threading
import time
import logging
import re
from bs4 import BeautifulSoup

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Global variables to store scraped data and lock for thread safety
scraped_data = None
data_lock = threading.Lock()

# Genius Sports API URL
GENIUS_SPORTS_URL = "https://widget.wh.geniussports.com/widget//?G33W2J2NVSFX7RFPJKILG7T26AMY99"

def fetch_genius_sports_data():
    try:
        response = requests.get(GENIUS_SPORTS_URL, timeout=10)
        response.raise_for_status()
        js_content = response.text

        match = re.search(r'var html = "(.*?)(?<!\\)";', js_content, re.DOTALL)

        if not match:
            print("No embedded HTML found!")
            return {"live_games": [], "all_games": []}
        
        html_content = match.group(1).replace('\\"', '"').replace('\\/', '/')  # Fix escaped quotes and slashes
        
        soup = BeautifulSoup(html_content, 'html.parser')
        matches = {"all_games": [], "live_games": []}

        for match_item in soup.find_all('li', class_='spls_lsmatch'):
            match_data = {}
            link_tag = match_item.find('a')

            if link_tag:
                match_data['match_link'] = link_tag.get('href', '')

            match_status = match_item.find('span', class_='spls_matchstatus')
            match_data['status'] = match_status.text.strip() if match_status else "N/A"

            match_comp = match_item.find('span', class_='spls_matchcomp')
            match_data['competition'] = match_comp.text.strip() if match_comp else "N/A"

            match_date = match_item.find('span', class_='spls_datefield')
            match_data['date'] = match_date.text.strip() if match_date else "N/A"

            teams = match_item.find_all('span', class_='spteam')
            match_data['teams'] = []

            for team in teams:
                team_data = {}
                team_name = team.find('span', class_='teamname')
                team_score = team.find('span', class_='score')
                team_logo = team.find('img')

                team_data['name'] = team_name.text.strip() if team_name else "Unknown"
                team_data['score'] = team_score.text.strip() if team_score else "N/A"
                team_data['logo'] = team_logo.get('src', '') if team_logo else "No logo"

                match_data['teams'].append(team_data)

            # Decode Unicode escape sequences before appending
            match_data['competition'] = match_data['competition'].encode('utf-8').decode('unicode_escape')
            for team in match_data['teams']:
                team['name'] = team['name'].encode('utf-8').decode('unicode_escape')

            if match_data['status'].lower() == "upcoming":
                matches["all_games"].append(match_data)
            else:
                matches["live_games"].append(match_data)
        return matches

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching Genius Sports data: {e}")
        return {"live_games": [], "all_games": []}



def continuous_scraper():
    """Continuously updates data every 90 seconds."""
    global scraped_data
    logging.info("Starting continuous scraper")

    while True:
        try:
            new_data = fetch_genius_sports_data()
            if not isinstance(new_data, dict):
                logging.error(f"Expected a dict but got {type(new_data)}. Converting the data.")
                # If new_data is a list assume it represents all_games and live_games is empty
                new_data = {"all_games": new_data if isinstance(new_data, list) else [], "live_games": []}
            with data_lock:
                scraped_data = new_data
            logging.info("Successfully updated game data")
        except Exception as e:
            logging.error(f"Scraping error: {str(e)}")
        time.sleep(15)  # Wait 90 seconds between scrapes


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/games')
def get_games():
    """Return the latest scraped data with non-escaped Unicode."""
    global scraped_data
    with data_lock:
        if scraped_data is None:
            return jsonify({"error": "Data not available yet"}), 503
        json_str = json.dumps(scraped_data, ensure_ascii=False)
        return app.response_class(json_str, mimetype='application/json')


@app.route('/api/scraper_status')
def scraper_status():
    """Return the status of the scraper."""
    global scraped_data
    with data_lock:
        if scraped_data is None:
            return jsonify({"status": "Scraper not yet initialized"}), 200
        return jsonify({"status": "Scraper running", "data_count": len(scraped_data['all_games'])}), 200


# Start background scraper thread
scraper_thread = threading.Thread(target=continuous_scraper, daemon=True)
scraper_thread.start()

if __name__ == '__main__':
    app.run(debug=True, port=8000)
