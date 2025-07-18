import json
import os
import threading
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

users_file = "users.json"

def load_users():
    if not os.path.exists(users_file):
        return {}
    try:
        with open(users_file, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

users = load_users()

def save_users():
    with open(users_file, "w") as f:
        json.dump(users, f)

def get_lastfm_nowplaying(username):
    url = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}&api_key={LASTFM_API_KEY}&format=json&limit=1"
    r = requests.get(url).json()
    track = r['recenttracks']['track'][0]
    if '@attr' in track and track['@attr']['nowplaying'] == 'true':
        return track['artist']['#text'], track['name']
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""🎧 Bem-vindo ao Vampirizer 🩸

Comandos:
/reglast <seu_user_lastfm>
/regspotify
/vampirizar <user_lastfm_da_vitima>
""")

async def reglast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if len(context.args) == 0:
        await update.message.reply_text("Uso: /reglast <seu_user_lastfm>")
        return
    users.setdefault(user_id, {})['lastfm_user'] = context.args[0]
    save_users()
    await update.message.reply_text(f"Registrado seu Last.fm como {context.args[0]}")

async def regspotify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                            client_secret=SPOTIPY_CLIENT_SECRET,
                            redirect_uri=SPOTIPY_REDIRECT_URI,
                            scope="user-modify-playback-state user-read-playback-state",
                            cache_path=f".cache-{user_id}")

    auth_url = sp_oauth.get_authorize_url(state=user_id)

    users.setdefault(user_id, {})['spotify_oauth_cache'] = f".cache-{user_id}"
    save_users()
    await update.message.reply_text(f"Clique para conectar o Spotify:\n{auth_url}")

def vampirizar_loop(user_id, vitima_lastfm):
    sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                            client_secret=SPOTIPY_CLIENT_SECRET,
                            redirect_uri=SPOTIPY_REDIRECT_URI,
                            scope="user-modify-playback-state user-read-playback-state",
                            cache_path=f".cache-{user_id}")

    sp = Spotify(auth_manager=sp_oauth)
    last_track = None

    while True:
        artist, track = get_lastfm_nowplaying(vitima_lastfm)
        if artist and track:
            if last_track != (artist, track):
                print(f"[{user_id}] Tocando: {artist} - {track}")
                result = sp.search(q=f"{track} {artist}", type='track', limit=1)
                if result['tracks']['items']:
                    uri = result['tracks']['items'][0]['uri']
                    sp.start_playback(uris=[uri])
                last_track = (artist, track)
        time.sleep(10)

async def vampirizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if len(context.args) == 0:
        await update.message.reply_text("Uso: /vampirizar <vitima_lastfm>")
        return
    vitima = context.args[0]
    await update.message.reply_text(f"Vampirizando {vitima} 🧛🎧")
    threading.Thread(target=vampirizar_loop, args=(user_id, vitima), daemon=True).start()

def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reglast", reglast))
    app.add_handler(CommandHandler("regspotify", regspotify))
    app.add_handler(CommandHandler("vampirizar", vampirizar))
    app.run_polling()

# Flask App para receber o callback do Spotify
flask_app = Flask(__name__)

@flask_app.route('/callback')
def callback():
    code = request.args.get('code')
    user_id = request.args.get('state')

    sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                            client_secret=SPOTIPY_CLIENT_SECRET,
                            redirect_uri=SPOTIPY_REDIRECT_URI,
                            scope="user-modify-playback-state user-read-playback-state",
                            cache_path=f".cache-{user_id}")

    token_info = sp_oauth.get_access_token(code)
    return "✅ Spotify conectado! Agora você pode usar /vampirizar no bot."

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
