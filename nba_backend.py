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
    """Create a requests session with retries and timeouts."""
    retry = Retry(
        total=5,
        backoff_factor=2,  # Wait longer between retries
        allowed_methods=["GET", "POST"],
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.timeout = (10, 60)  # Connect timeout: 10s, Read timeout: 60s
    return session



session = create_session()


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

# Function: Get today's games
def get_today_games():
    try:
        response = session.get('https://stats.nba.com')
        if response.status_code == 429:  # Too many requests
            logging.warning("Rate limited by the NBA API. Retrying after delay...")
            time.sleep(60)  # Wait 1 minute before retrying
            return []
        
        scoreboard = scoreboardv2.ScoreboardV2(day_offset=0)
        games = scoreboard.get_data_frames()[0]
        today_games = []
        for _, game in games.iterrows():
            game_id = game['GAME_ID']
            home_team = game['HOME_TEAM_ID']
            away_team = game['VISITOR_TEAM_ID']
            game_status = game['GAME_STATUS_TEXT'].strip().lower()

            game_data[game_id] = {
                'home_team': home_team,
                'away_team': away_team,
                'status': 'live' if 'live' in game_status or 'qtr' in game_status else game_status,
                'last_event': None,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            today_games.append(game_id)
        return today_games
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error: {str(e)}")
        return []
    except Exception as e:
        logging.error(f"Error retrieving today's games: {str(e)}")
        return []


# Function: Track today's games
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

# Function: Process game events
def process_game_events(game_id):
    try:
        pbp = playbyplayv2.PlayByPlayV2(game_id=game_id)
        pbp_data = pbp.get_data_frames()[0]
        last_processed_event = game_data[game_id]['last_event']

        for index, row in pbp_data.iterrows():
            event_num = row['EVENTNUM']
            if last_processed_event and event_num <= last_processed_event:
                continue  # Skip already processed events

            game_data[game_id]['last_event'] = event_num

            # Missed shot detection
            if row['EVENTMSGTYPE'] == 2:  # Missed shot
                for i in range(index + 1, index + 4):  # Check next 3 events
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
                                logging.info(f"Flagged team rebound for game {game_id} at {row['PCTIMESTRING']}")
                            break
                else:
                    # No rebound event found
                    flagged_rebounds.setdefault(game_id, []).append({
                        "timestamp": row['PCTIMESTRING'],
                        "quarter": row['PERIOD'],
                        "description": row['HOMEDESCRIPTION'] or row['VISITORDESCRIPTION'],
                        "reason": "Potential missed rebound: No rebound credited."
                    })
                    logging.info(f"Flagged missed rebound for game {game_id} at {row['PCTIMESTRING']}")
    except Exception as e:
        logging.error(f"Error processing game {game_id}: {str(e)}")

import os

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Use PORT from the environment or default to 5000
    app.run(port=port, host='0.0.0.0', debug=True)
