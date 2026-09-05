# -*- coding: utf-8 -*-
import asyncio
import os
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
