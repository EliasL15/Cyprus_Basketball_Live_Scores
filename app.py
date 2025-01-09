from flask import Flask, render_template, jsonify
from flask_caching import Cache
from playwright.sync_api import sync_playwright
import re
from datetime import datetime
from flask_apscheduler import APScheduler

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

scraped_data = {}

def scrape_dynamic_content():
    live_games = []
    all_games = []
    current_month = datetime.now().strftime('%m')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.cbf.basketball/")
        
        page.wait_for_selector('.mbt-game-scroller-v2-game')
        games = page.query_selector_all('.mbt-game-scroller-v2-game')
        
        for game in games:
            team_a_name = game.query_selector('.mbt-game-scroller-v2-teams-team-a-name').inner_text()
            team_a_score = game.query_selector('.mbt-game-scroller-v2-teams-team-a-score').inner_text()
            team_b_name = game.query_selector('.mbt-game-scroller-v2-teams-team-b-name').inner_text()
            team_b_score = game.query_selector('.mbt-game-scroller-v2-teams-team-b-score').inner_text()
            
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
    

    return {
        'live_games': live_games,
        'all_games': all_games
    }

def scheduled_scrape():
    global scraped_data
    scraped_data = scrape_dynamic_content()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/games')
def get_games():
    return jsonify(scraped_data)

if __name__ == '__main__':
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.start()
    scheduler.add_job(id='ScrapeJob', func=scheduled_scrape, trigger='interval', minutes=2)
    
    # Run the scrape function immediately on startup
    scheduled_scrape()
    
    app.run(debug=True, port=8000)