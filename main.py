import os
import json
import asyncio
import time
import requests
from dotenv import load_dotenv
from flask import Flask, request
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # URL pública do seu webhook

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
    if '@attr' in track and track['@attr'].get('nowplaying') == 'true':
        return track['artist']['#text'], track['name']
    return None, None

app = Application.builder().token(TELEGRAM_TOKEN).build()

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
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope="user-modify-playback-state user-read-playback-state",
        cache_path=f".cache-{user_id}"
    )
    auth_url = sp_oauth.get_authorize_url(state=user_id)
    await update.message.reply_text(f"Clique para conectar o Spotify:\n{auth_url}")

async def vampirizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if len(context.args) == 0:
        await update.message.reply_text("Uso: /vampirizar <vitima_lastfm>")
        return
    vitima = context.args[0]
    await update.message.reply_text(f"Vampirizando {vitima} 🧛🎧")
    context.application.create_task(vampirizar_loop(user_id, vitima))

async def vampirizar_loop(user_id, vitima_lastfm):
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope="user-modify-playback-state user-read-playback-state",
        cache_path=f".cache-{user_id}"
    )
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
        await asyncio.sleep(10)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("reglast", reglast))
app.add_handler(CommandHandler("regspotify", regspotify))
app.add_handler(CommandHandler("vampirizar", vampirizar))

flask_app = Flask(__name__)
async_loop = None  # guardaremos o loop aqui

@flask_app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = Update.de_json(request.json, app.bot)
    asyncio.run(app.process_update(update))
    return "OK"

@flask_app.route('/callback')
def callback():
    code = request.args.get('code')
    user_id = request.args.get('state')
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope="user-modify-playback-state user-read-playback-state",
        cache_path=f".cache-{user_id}"
    )
    sp_oauth.get_access_token(code=code, as_dict=False)
    return "✅ Spotify conectado! Agora você pode usar /vampirizar no bot."

if __name__ == "__main__":
    async def main():
        global async_loop
        await app.initialize()
        await app.bot.set_webhook(url=WEBHOOK_URL)
        await app.start()
        async_loop = asyncio.get_running_loop()
        flask_app.run(host="0.0.0.0", port=8080)

    asyncio.run(main())

