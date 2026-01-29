import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
# GUILD_ID is no longer strictly needed for single-server sync, leaving as optional
GUILD_ID = int(os.getenv("GUILD_ID", 0))

# Dynamic roles are now used, so these are removed/ignored
NGROK_DOMAIN = os.getenv("NGROK_DOMAIN")
ROOT_ADMIN_ID = int(os.getenv("ROOT_ADMIN_ID", 0))

# Turso Cloud SQLite
TURSO_URL = os.getenv("TURSO_URL")
TURSO_TOKEN = os.getenv("TURSO_TOKEN")

if not REDIRECT_URI:
    REDIRECT_URI = "http://localhost:8080/callback"
