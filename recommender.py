import pandas as pd
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
import pandas as pd
import re
from sklearn.feature_extraction.text import TfidfVectorizer
import requests
import os

def normalize(name):
    name = name.lower().strip()
    name = name.replace("'", " ")                    # apostrophe → space (not removed)
    name = re.sub(r'[™®©:\"\!,.]', '', name)        # remove other punctuation
    name = re.sub(r'\s+', ' ', name).strip()         # collapse spaces
    return name

#df = pd.read_csv("hybrid_training_dataset.csv")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(BASE_DIR, "hybrid_training_dataset.csv")

df = pd.read_csv(csv_path)

df_content = df[['game_title', 'combined_tags']].drop_duplicates('game_title').copy()
df_content['combined_tags'] = df_content['combined_tags'].fillna('').astype(str)
df_content = df_content.reset_index(drop=True)

tfidf = TfidfVectorizer(stop_words='english')
tfidf_matrix = tfidf.fit_transform(df_content['combined_tags'])

content_game_to_idx = {normalize(title): i for i, title in enumerate(df_content['game_title'])}
content_idx_to_game = {i: title for i, title in enumerate(df_content['game_title'])}

tfidf = TfidfVectorizer(stop_words='english')
tfidf_matrix = tfidf.fit_transform(df_content['combined_tags'])


ratings = df[['user_id', 'game_title', 'rating']].dropna().copy()

ratings['user_id'] = ratings['user_id'].astype(str)
ratings['game_title'] = ratings['game_title'].astype(str)

ratings['user_idx'] = ratings['user_id'].astype('category').cat.codes
ratings['item_idx'] = ratings['game_title'].astype('category').cat.codes

num_users = ratings['user_idx'].nunique()
num_items = ratings['item_idx'].nunique()

print("Users:", num_users, " Items:", num_items)
ratings.head()

df = df.dropna(subset=['rating', 'game_title'])
df['game_title'] = df['game_title'].astype(str)
df['user_id'] = df['user_id'].astype(str)

ratings['user_idx'] = ratings['user_idx'].astype(int)
ratings['item_idx'] = ratings['item_idx'].astype(int)

data = ratings[['user_idx', 'item_idx', 'rating']].copy()

train, test = train_test_split(data, test_size=0.2, random_state=42)

train['user_idx'] = train['user_idx'].astype(int)
train['item_idx'] = train['item_idx'].astype(int)

test['user_idx'] = test['user_idx'].astype(int)
test['item_idx'] = test['item_idx'].astype(int)


ratings['user_idx'] = ratings['user_id'].astype('category').cat.codes
ratings['item_idx'] = ratings['game_title'].astype('category').cat.codes

num_users = ratings['user_idx'].nunique()
num_items = ratings['item_idx'].nunique()

print("Users:", num_users, " Items:", num_items)

user_item_matrix = csr_matrix(
    (ratings['rating'], (ratings['user_idx'], ratings['item_idx'])),
    shape=(num_users, num_items)
)


item_similarity = cosine_similarity(user_item_matrix.T)
item_similarity.shape

def recommend_for_steam_user(steam_games, top_n=5):
    user_vector = build_user_vector_from_steam(steam_games)
    rated_items = np.where(user_vector > 0)[0]
    print(f"Matched {len(rated_items)} games")
    if len(rated_items) < 1:
        print("Cold start triggered — returning popular games")
        return get_popular_steam_games(top_n)

    matched_titles = [idx_to_game[i] for i in rated_items]
    print(f"Matched {len(matched_titles)} games: {matched_titles}")

    if len(rated_items) == 0:
        return []

    # --- Collaborative filtering scores ---
    cf_scores = item_similarity[:, rated_items].dot(user_vector[rated_items])
    sim_sums = np.abs(item_similarity[:, rated_items]).sum(axis=1)
    cf_scores = cf_scores / np.maximum(sim_sums, 1e-8)
    cf_scores[rated_items] = -np.inf

    # --- Content-based scores ---
    content_scores = np.zeros(len(df_content))
    for title in matched_titles:
        n = normalize(title)
        if n in content_game_to_idx:
            idx = content_game_to_idx[n]
            sims = cosine_similarity(tfidf_matrix[idx], tfidf_matrix).flatten()
            content_scores += sims

    # Align content_scores to cf_scores space via game title
    final_scores = np.zeros(num_items)
    for iidx in range(num_items):
        game = idx_to_game[iidx]
        n = normalize(game)
        cf = float(cf_scores[iidx]) if cf_scores[iidx] != -np.inf else 0.0
        cb = 0.0
        if n in content_game_to_idx:
            c_idx = content_game_to_idx[n]
            if c_idx < len(content_scores):  # bounds check
                cb = float(content_scores[c_idx])
        final_scores[iidx] = 0.4 * cf + 0.6 * cb

    final_scores[rated_items] = -np.inf
    top_idx = np.argsort(final_scores)[-top_n:][::-1]

    print("Final scores:", [round(final_scores[i], 4) for i in top_idx])

    return [
        {"game": idx_to_game[i], "score": round(float(final_scores[i]), 4)}
        for i in top_idx
    ]
def predict_rating(uidx, iidx, train_item_sim, train_matrix):
    user_row = train_matrix.getrow(uidx).toarray().flatten()

    rated = np.where(user_row > 0)[0]
    if len(rated) == 0:

        return user_row[user_row > 0].mean() if user_row[user_row > 0].size > 0 else 5.0

    sims = train_item_sim[iidx, rated]

    ratings_rated = user_row[rated]
    denom = np.sum(np.abs(sims))
    if denom == 0:
        return ratings_rated.mean()
    return np.dot(sims, ratings_rated) / denom

errors = []
train_matrix = csr_matrix(
    (train['rating'], (train['user_idx'], train['item_idx'])),
    shape=(num_users, num_items)
)

train_item_sim = cosine_similarity(train_matrix.T)
for _, row in test.iterrows():
    uidx = int(row['user_idx'])
    iidx = int(row['item_idx'])

    if uidx >= train_matrix.shape[0] or iidx >= train_matrix.shape[1]:
        continue

    true = row['rating']
    pred = predict_rating(uidx, iidx,train_item_sim,train_matrix)
    errors.append((true - pred) ** 2)

idx_to_game = dict(enumerate(ratings['game_title'].astype('category').cat.categories))
game_to_idx = {v: k for k, v in idx_to_game.items()}
game_to_idx_lower = {normalize(k): v for k, v in game_to_idx.items()}
idx_to_user = dict(enumerate(ratings['user_id'].astype('category').cat.categories))
user_to_idx = {v: k for k, v in idx_to_user.items()}

def recommend_for_user(user_id, n=5):
    user_id = str(user_id)

    if user_id not in user_to_idx:
        print("❌ User not found in dataset.")
        return

    uidx = user_to_idx[user_id]


    user_vector = user_item_matrix.getrow(uidx).toarray().flatten()


    rated_items = np.where(user_vector > 0)[0]

    if len(rated_items) == 0:
        print("❌ This user has no ratings.")
        return


    scores = item_similarity[:, rated_items].dot(user_vector[rated_items])

    sim_sums = np.abs(item_similarity[:, rated_items]).sum(axis=1)
    sim_sums[sim_sums == 0] = 1e-8
    scores = scores / sim_sums


    scores[rated_items] = -np.inf


    top_idx = np.argsort(scores)[-n:][::-1]

    print(f"\n🎮 Top {n} Recommended Games for User {user_id}:")
    for idx in top_idx:
        print(f"  • {idx_to_game[idx]}   (score: {scores[idx]:.2f})")


data = ratings[['user_idx', 'item_idx', 'rating']].copy()

train, test = train_test_split(data, test_size=0.2, random_state=42)





def get_recommendations(user_id, top_n=5):
    user_id = str(user_id)

    # use existing mapping
    if user_id not in user_to_idx:
        return []

    uid = user_to_idx[user_id]
    scores = []

    for iidx in range(train_matrix.shape[1]):
        score = predict_rating(
            uid,
            iidx,
            train_item_sim,
            train_matrix
        )
        scores.append((iidx, score))

    scores.sort(key=lambda x: x[1], reverse=True)

    top_items = scores[:top_n]

    recommendations = []
    for iidx, score in top_items:
        recommendations.append({
            "game": idx_to_game[iidx],
            "score": float(score)
        })

    return recommendations


def build_user_vector_from_steam(steam_games):
    user_vector = np.zeros(num_items)
    matched = []

    for game in steam_games:
        name = normalize(game.get("name", ""))
        playtime = game.get("playtime_forever", 0)
        if name in game_to_idx_lower and playtime > 0:
            matched.append((name, playtime, game_to_idx_lower[name]))

    if not matched:
        return user_vector

    # Scale playtime relatively across matched games (1–10)
    max_playtime = max(p for _, p, _ in matched)

    for name, playtime, idx in matched:
        rating = max(1, round((playtime / max_playtime) * 10))
        user_vector[idx] = rating
        print(f"  {name}: {playtime} mins -> rating {rating}")

    return user_vector

def get_popular_steam_games(top_n=5):
    print("Fetching popular games from Steam...")
    url = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
    response = requests.get(url, timeout=10).json()
    ranks = response["response"]["ranks"]

    popular = []
    for i, game in enumerate(ranks):
        if len(popular) >= top_n:
            break
        appid = str(game["appid"])
        details = requests.get(
            f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic",
            timeout=8
        ).json()
        if details and details.get(appid, {}).get("success"):
            name = details[appid]["data"]["name"]
            popular.append({
                "game": name,
                "score": round(1 - (i / top_n), 4),
                "cold_start": True
            })
            print(f"  Fetched: {name}")

    print(f"Fetched {len(popular)} popular games")
    return popular

rmse = np.sqrt(np.mean(errors))
print("📉 RMSE:", rmse)

u = ratings['user_id'].sample(1).iloc[0]
recommend_for_user(u, n=5)

print(ratings['user_id'].unique()[:10])
