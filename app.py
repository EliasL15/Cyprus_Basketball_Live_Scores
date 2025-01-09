from flask import Flask, render_template, jsonify
from flask_caching import Cache
from playwright.sync_api import sync_playwright
import re
from datetime import datetime

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

def scrape_dynamic_content():
    live_games = []
    all_games = []
    current_month = datetime.now().strftime('%m')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.cbf.basketball/")
        
        # Wait for the dynamic content to load
        page.wait_for_selector('.mbt-game-scroller-v2-game')

        # Extract content of all game elements and filter live games
        games = page.query_selector_all('.mbt-game-scroller-v2-game')
        for game in games:
            team_a_name = game.query_selector('.mbt-game-scroller-v2-teams-team-a-name').inner_text()
            team_a_score = game.query_selector('.mbt-game-scroller-v2-teams-team-a-score').inner_text()
            team_b_name = game.query_selector('.mbt-game-scroller-v2-teams-team-b-name').inner_text()
            team_b_score = game.query_selector('.mbt-game-scroller-v2-teams-team-b-score').inner_text()
            
            # Extract URL from the href attribute
            href = game.get_attribute('href')
            match = re.search(r"window\.open\('([^']+)'", href)
            game_url = match.group(1) if match else None
            if game_url is None:
                game_url = f"https://www.cbf.basketball/{href}"
            
            # Extract quarter, time left, date, and league name
            quarter = game.query_selector('.mbt-game-scroller-v2-game-info-time').inner_text().strip()
            time_left = game.evaluate('(element) => element.nextSibling.textContent', game.query_selector('.mbt-game-scroller-v2-game-info-time')).strip()
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

        # Sort all games by date and time_left attribute
        all_games.sort(key=lambda x: (x['date'], x['time_left']), reverse=True)

        browser.close()
    return live_games, all_games

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/live-scores')
@cache.cached(timeout=60)
def live_scores():
    live_games, _ = scrape_dynamic_content()
    return jsonify(live_games)

@app.route('/api/all-games')
@cache.cached(timeout=60)
def all_games():
    _, all_games = scrape_dynamic_content()
    return jsonify(all_games)

if __name__ == '__main__':
    app.run(debug=True, port=5001)