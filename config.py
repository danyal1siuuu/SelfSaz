# -*- coding: utf-8 -*-
import os

API_ID = int(os.getenv("API_ID", "1234567"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_LOG = int(os.getenv("CHANNEL_LOG", "0"))

AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")

DB_NAME = "database/selfsaz.db"
DOWNLOAD_DIR = "downloads/"
