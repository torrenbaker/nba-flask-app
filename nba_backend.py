from flask import Flask, jsonify
from nba_api.stats.endpoints import scoreboardv2, playbyplayv2
from datetime import datetime
from flask_cors import CORS
import time
import logging
import threading
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# In-memory storage for game data and flagged rebounds
game_data = {}
flagged_rebounds = {}

# Mapping of team IDs to team names
TEAM_NAMES = {
    "1610612737": "Hawks",
    "1610612738": "Celtics",
    "1610612739": "Cavaliers",
    "1610612740": "Pelicans",
    "1610612741": "Bulls",
    "1610612742": "Mavericks",
    "1610612743": "Nuggets",
    "1610612744": "Warriors",
    "1610612745": "Rockets",
    "1610612746": "Clippers",
    "1610612747": "Lakers",
    "1610612748": "Heat",
    "1610612749": "Bucks",
    "1610612750": "Timberwolves",
    "1610612751": "Nets",
    "1610612752": "Knicks",
    "1610612753": "Magic",
    "1610612754": "Pacers",
    "1610612755": "76ers",
    "1610612756": "Suns",
    "1610612757": "Trail Blazers",
    "1610612758": "Kings",
    "1610612759": "Spurs",
    "1610612760": "Thunder",
    "1610612761": "Raptors",
    "1610612762": "Jazz",
    "1610612763": "Grizzlies",
    "1610612764": "Wizards",
    "1610612765": "Pistons",
    "1610612766": "Hornets"
}


def create_session():
    """Create a requests session with retries, timeouts, and ScraperAPI proxy."""
    retry = Retry(
        total=5,  # Retry up to 5 times
        backoff_factor=2,  # Exponential backoff
        allowed_methods=["GET", "POST"],
        status_forcelist=[429, 500, 502, 503, 504]  # Retry on these status codes
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.timeout = (10, 120)  # Timeout: 10s connect, 120s read

    # Use ScraperAPI proxy
    scraper_api_url = f"http://api.scraperapi.com?api_key=5691e6d3b6b3751098287717895e7c0b"
    session.proxies = {
        "http": scraper_api_url,
        "https": scraper_api_url
   
    }
    
    # Add logging to confirm proxies
    logging.info(f"Using proxy: {session.proxies}")
    
    return session




def track_today_games():
    try:
        today_games = get_today_games()
        if not today_games:
            logging.info("No games found for today.")
            return
        
        logging.info(f"Tracking games: {today_games}")
        while True:
            active_games = [game_id for game_id in today_games if game_data[game_id]['status'].lower() == 'live']
            for game_id in active_games:
                process_game_events(game_id)
                game_data[game_id]['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            time.sleep(30)  # Poll every 30 seconds
    except Exception as e:
        logging.error(f"Error tracking games: {str(e)}")


# Endpoint: Start live tracking
@app.route('/api/start-live-tracking', methods=['GET'])
def start_live_tracking():
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        logging.info(f"Starting live tracking for today's games: {today}")
        threading.Thread(target=track_today_games).start()  # Run tracking in a separate thread
        return jsonify({"message": "Live tracking initiated for today's games."})
    except Exception as e:
        logging.error(f"Error starting live tracking: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
def test_connectivity():
    try:
        response = requests.get("https://stats.nba.com", timeout=10)
        if response.status_code == 200:
            logging.info("Successfully connected to stats.nba.com")
        else:
            logging.error(f"Failed to connect to stats.nba.com. Status code: {response.status_code}")
    except Exception as e:
        logging.error(f"Connectivity test failed: {str(e)}")


# Endpoint: Tracking status
@app.route('/api/tracking-status', methods=['GET'])
def get_tracking_status():
    try:
        games_being_tracked = len([game_id for game_id in game_data if game_data[game_id]['status'].lower() == 'live'])
        return jsonify({
            "games_being_tracked": games_being_tracked,
            "flagged_rebounds": sum(len(rebounds) for rebounds in flagged_rebounds.values()),
            "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        logging.error(f"Error fetching tracking status: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Endpoint: Game status
@app.route('/api/game-status', methods=['GET'])
def get_game_status():
    try:
        games = []
        for game_id, data in game_data.items():
            games.append({
                "game_id": game_id,
                "home_team": TEAM_NAMES.get(str(data['home_team']), "Unknown"),
                "away_team": TEAM_NAMES.get(str(data['away_team']), "Unknown"),
                "status": data['status'],
                "last_updated": data.get('last_updated', "N/A")
            })
        return jsonify({"games": games})
    except Exception as e:
        logging.error(f"Error fetching game status: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Endpoint: Flagged rebounds
@app.route('/api/flagged-rebounds', methods=['GET'])
def get_flagged_rebounds():
    try:
        flattened_rebounds = []
        for game_id, rebounds in flagged_rebounds.items():
            game = game_data.get(game_id, {})
            home_team_name = TEAM_NAMES.get(str(game.get('home_team')), "Unknown")
            away_team_name = TEAM_NAMES.get(str(game.get('away_team')), "Unknown")
            for rebound in rebounds:
                flattened_rebounds.append({
                    **rebound,
                    "game_id": game_id,
                    "home_team": home_team_name,
                    "away_team": away_team_name
                })
        return jsonify({"flagged_rebounds": flattened_rebounds})
    except Exception as e:
        logging.error(f"Error fetching flagged rebounds: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/test-scraperapi', methods=['GET'])
def test_scraperapi():
    try:
        proxy_url = "http://api.scraperapi.com?api_key=5691e6d3b6b3751098287717895e7c0b"
        proxies = {"http": proxy_url, "https": proxy_url}
        
        # Test the connection to stats.nba.com through ScraperAPI
        response = requests.get("https://stats.nba.com/stats/scoreboardv2", proxies=proxies, timeout=60)
        return jsonify({"status_code": response.status_code, "response": response.text[:500]})  # Show part of the response
    except Exception as e:
        logging.error(f"ScraperAPI test failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/test-connectivity', methods=['GET'])
def test_connectivity_endpoint():
    try:
        # Check connectivity to stats.nba.com
        response = session.get("https://stats.nba.com", timeout=10)
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Successfully connected to stats.nba.com"}), 200
        else:
            return jsonify({"status": "failure", "message": f"Unexpected status code: {response.status_code}"}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def get_today_games():
    try:
        logging.info("Retrieving today's games using nba_api library.")
        
        # Measure the response time for the API call
        start_time = time.time()
        try:
            scoreboard = scoreboardv2.ScoreboardV2(day_offset=0)
            response_time = time.time() - start_time
            logging.info(f"ScoreboardV2 API response time: {response_time:.2f} seconds")
        except Exception as e:
            logging.error(f"Error during API request: {str(e)}")
            return []

        # Extract the game data from the returned DataFrame
        try:
            games = scoreboard.get_data_frames()[0]
            if games.empty:
                logging.info("No games found for today.")
                return []
        except Exception as e:
            logging.error(f"Error processing API response: {str(e)}")
            return []

        # Debugging API Response
        logging.info(f"Number of games retrieved: {len(games)}")
        logging.info(f"Sample of data: {games.head(3).to_dict(orient='records')}")  # Log a sample of the game data
        
        today_games = []
        for _, game in games.iterrows():
            game_id = game['GAME_ID']
            home_team = game['HOME_TEAM_ID']
            away_team = game['VISITOR_TEAM_ID']
            game_status = game['GAME_STATUS_TEXT'].strip().lower()

            # Update in-memory game data
            game_data[game_id] = {
                'home_team': home_team,
                'away_team': away_team,
                'status': 'live' if 'live' in game_status or 'qtr' in game_status else game_status,
                'last_event': None,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            today_games.append(game_id)

        logging.info(f"Retrieved games: {today_games}")
        return today_games

    except Exception as e:
        logging.error(f"Error retrieving today's games: {str(e)}")
        return []



# Function: Track today's games
def process_game_events(game_id):
    try:
        start_time = time.time()  # Start timing
        logging.info(f"Processing game events for game_id: {game_id}")

        # Fetch play-by-play data
        pbp = playbyplayv2.PlayByPlayV2(game_id=game_id)
        pbp_data = pbp.get_data_frames()[0]
        logging.info(f"Retrieved {len(pbp_data)} events for game_id: {game_id}")

        last_processed_event = game_data[game_id].get('last_event')

        for index, row in pbp_data.iterrows():
            event_num = row['EVENTNUM']

            # Skip already processed events
            if last_processed_event and event_num <= last_processed_event:
                continue

            # Update the last processed event
            game_data[game_id]['last_event'] = event_num

            # Detect missed shot leading to potential rebound
            if row['EVENTMSGTYPE'] == 2:  # Missed shot
                logging.debug(f"Missed shot detected at event {event_num} for game_id: {game_id}")

                # Check subsequent events for rebounds
                rebound_flagged = False
                for i in range(index + 1, index + 4):  # Look at the next 3 events
                    if i < len(pbp_data):
                        next_event = pbp_data.iloc[i]
                        if next_event['EVENTMSGTYPE'] == 4:  # Rebound event
                            if "Team Rebound" in (next_event['HOMEDESCRIPTION'] or next_event['VISITORDESCRIPTION']):
                                flagged_rebounds.setdefault(game_id, []).append({
                                    "timestamp": row['PCTIMESTRING'],
                                    "quarter": row['PERIOD'],
                                    "description": row['HOMEDESCRIPTION'] or row['VISITORDESCRIPTION'],
                                    "reason": "Potential misattribution: Team rebound instead of individual."
                                })
                                logging.info(f"Flagged team rebound for game_id {game_id} at {row['PCTIMESTRING']}")
                                rebound_flagged = True
                                break
                
                # If no rebound is flagged within the next 3 events
                if not rebound_flagged:
                    flagged_rebounds.setdefault(game_id, []).append({
                        "timestamp": row['PCTIMESTRING'],
                        "quarter": row['PERIOD'],
                        "description": row['HOMEDESCRIPTION'] or row['VISITORDESCRIPTION'],
                        "reason": "Potential missed rebound: No rebound credited."
                    })
                    logging.info(f"Flagged missed rebound for game_id {game_id} at {row['PCTIMESTRING']}")

        logging.info(f"Finished processing game_id: {game_id} in {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logging.error(f"Error processing game_id {game_id}: {str(e)}")


import os

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Use PORT from the environment or default to 5000
    app.run(port=port, host='0.0.0.0', debug=True)
