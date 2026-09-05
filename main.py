# -*- coding: utf-8 -*-
import asyncio
import os
import pyrogram.utils

# رفع باگ کانال‌ها و گروه‌های جدید تلگرام در پایروگرام
def get_peer_type_new(peer_id: int) -> str:
    peer_id_str = str(peer_id)
    if not peer_id_str.startswith("-"):
        return "user"
    elif peer_id_str.startswith("-100"):
        return "channel"
    else:
        return "chat"

pyrogram.utils.get_peer_type = get_peer_type_new
pyrogram.utils.MIN_CHANNEL_ID = -100999999999999
pyrogram.utils.MIN_CHAT_ID = -99999999999999

from config import DB_NAME
from database.db import init_db
from host_bot.bot import bot
from core.manager import launch_all_existing_selfs

async def main():
    os.makedirs("downloads", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    os.makedirs("database", exist_ok=True)
    print("🔄 Initializing DB...")
    await init_db()
    
    print("🤖 Starting Maker Bot...")
    asyncio.create_task(bot.start())
    
    print("⚡ Launching all saved selfbots...")
    await launch_all_existing_selfs()
    
    print("🚀 TeleBotCraft Multi-Client Engine Online!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
