from flask import Flask, jsonify, render_template
from recommender import get_recommendations, recommend_for_steam_user, get_popular_steam_games
import requests
from flask import redirect, request, session
import os
STEAM_API_KEY = "5C7745FC550805A4DF119BF09307FE6F"

from flask import Flask

app = Flask(__name__)


app = Flask(__name__)
app.config["SECRET_KEY"] = "steam-recommender-secret-key"



@app.route("/")
def home():
    steam_id = session.get("steam_id")
    return render_template("index.html", steam_id=steam_id)


@app.route("/login")
def login():
    return redirect(
        "https://steamcommunity.com/openid/login"
        "?openid.ns=http://specs.openid.net/auth/2.0"
        "&openid.mode=checkid_setup"
        "&openid.return_to=http://localhost:5000/auth"
        "&openid.realm=http://localhost:5000"
        "&openid.identity=http://specs.openid.net/auth/2.0/identifier_select"
        "&openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select"
    )

@app.route("/auth")
def auth():
    steam_id = request.args.get("openid.claimed_id").split("/")[-1]
    session["steam_id"] = steam_id
    print("Logged in Steam ID:", steam_id)
    return redirect("/app")



def get_steam_games(steam_id):
    url = (
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        f"?key={STEAM_API_KEY}&steamid={steam_id}&include_appinfo=true"
    )
    response = requests.get(url).json()
    return response["response"].get("games", [])

@app.route("/steam-recommend")
def steam_recommend():
    steam_id = session.get("steam_id")

    if not steam_id:
        return jsonify({"error": "User not logged in"}), 401

    is_public, result = check_steam_profile_access(steam_id)

    if not is_public or not result:
        recs = get_popular_steam_games(top_n=5)
        return jsonify({"recommendations": recs})

    recs = recommend_for_steam_user(result, top_n=5)

    if not recs:
        recs = get_popular_steam_games(top_n=5)

    return jsonify({"recommendations": recs})

# 🔥 ADD THIS ROUTE
@app.route("/app")
def app_ui():
    steam_id = session.get("steam_id")
    return render_template("index.html", steam_id=steam_id)

def check_steam_profile_access(steam_id):
    url = (
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        f"?key={"5C7745FC550805A4DF119BF09307FE6F"}&steamid={steam_id}&include_appinfo=true"
    )

    response = requests.get(url).json()

    # If response structure is missing or games list is empty
    if "response" not in response:
        return False, "No response from Steam API"

    games = response["response"].get("games", [])

    if not games:
        return False, "Steam profile is private or has no games"

    return True, games

def get_steam_games_with_playtime(steam_id):
    url = (
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        f"?key={STEAM_API_KEY}"
        f"&steamid={steam_id}"
        "&include_appinfo=true"
        "&include_played_free_games=true"
        "&include_free_games=true"
    )

    response = requests.get(url).json()

    games = response.get("response", {}).get("games", [])

    formatted_games = []
    for g in games:
        formatted_games.append({
            "name": g.get("name"),
            "playtime_hours": round(g.get("playtime_forever", 0) / 60, 2)
        })

    return formatted_games


@app.route("/steam-games")
def steam_games():
    steam_id = session.get("steam_id")

    if not steam_id:
        return jsonify({"error": "User not logged in"}), 401

    games = get_steam_games_with_playtime(steam_id)

    if not games:
        return jsonify({"error": "Steam profile is private or has no games"}), 403

    return jsonify({
        "total_games": len(games),
        "games": games[:10]  # show first 10 for sanity check
    })


@app.route("/recommend/<user_id>")
def recommend(user_id):
    results = get_recommendations(user_id, top_n=5)

    if not results:
        return jsonify({"error": "User not found or has no ratings"}), 404

    return jsonify({"recommendations": results})

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)

app = Flask(__name__)
