from flask import Flask, redirect, request, session, jsonify, url_for
import requests
import re

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

STEAM_API_KEY = "5C7745FC550805A4DF119BF09307FE6F"
STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"

# ---------------------------------------------
# 1️⃣ Home Route
# ---------------------------------------------
@app.route('/')
def index():
    if 'steam_id' in session:
        return redirect(url_for('profile'))
    return '''
        <h1>Game Recommendation System</h1>
        <a href="/login"><button>Login with Steam</button></a>
    '''

# ---------------------------------------------
# 2️⃣ Steam Login (redirect user to Steam)
# ---------------------------------------------
@app.route('/login')
def login():
    # Create Steam OpenID login URL
    params = {
        'openid.ns': 'http://specs.openid.net/auth/2.0',
        'openid.mode': 'checkid_setup',
        'openid.return_to': request.host_url + 'authorize',
        'openid.realm': request.host_url,
        'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select'
    }

    query = '&'.join([f"{k}={v}" for k, v in params.items()])
    login_url = f"{STEAM_OPENID_URL}?{query}"

    return redirect(login_url)

# ---------------------------------------------
# 3️⃣ Steam Callback — User Authenticated
# ---------------------------------------------
@app.route('/authorize')
def authorize():

    params = request.args.to_dict()
    params['openid.mode'] = 'check_authentication'

    res = requests.post(STEAM_OPENID_URL, data=params)
    if "is_valid:true" not in res.text:
        return "Steam login failed. Please try again."

    match = re.search(r"https://steamcommunity.com/openid/id/(\d+)", request.args.get('openid.claimed_id'))
    if not match:
        return "Unable to retrieve Steam ID."

    steam_id = match.group(1)
    session['steam_id'] = steam_id
    return redirect(url_for('profile'))

@app.route('/profile')
def profile():
    if 'steam_id' not in session:
        return redirect(url_for('index'))

    steam_id = session['steam_id']

    api_url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": STEAM_API_KEY,
        "steamid": steam_id,
        "include_appinfo": True,
        "include_played_free_games": True,
        "format": "json"
    }

    res = requests.get(api_url, params=params)
    data = res.json()

    if "response" not in data or "games" not in data["response"]:
        return "<h3>Your Steam game data is private. Make it public to get recommendations.</h3>"

    games = data["response"]["games"]
    top_games = sorted(games, key=lambda x: x["playtime_forever"], reverse=True)[:5]

    return jsonify({
        "steam_id": steam_id,
        "top_games": [
            {"name": g["name"], "playtime_hours": g["playtime_forever"] // 60}
            for g in top_games
        ]
    })

# ---------------------------------------------
# 5️⃣ Logout Route
# ---------------------------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---------------------------------------------
# 6️⃣ Run Server
# ---------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)
