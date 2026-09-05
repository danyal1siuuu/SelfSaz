# -*- coding: utf-8 -*-
import asyncio
import os
import aiosqlite
from pyrogram import Client
from config import API_ID, API_HASH, DB_NAME
from database.db import init_db
from host_bot.bot import bot

clients = []

async def launch_selfs():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, session_string FROM users WHERE session_string IS NOT NULL")
        rows = await cursor.fetchall()
    for uid, sess in rows:
        try:
            cli = Client(
                name=f"self_{uid}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=sess,
                plugins=dict(root="plugins")
            )
            await cli.start()
            cli.custom_prefix = "."
            cli.prefix_enabled = True
            clients.append(cli)
            print(f"[+] Userbot for {uid} started.")
        except Exception as e:
            print(f"[-] Error on user {uid}: {e}")

async def main():
    os.makedirs("downloads", exist_ok=True)
    os.makedirs("database", exist_ok=True)
    print("🔄 Initializing DB...")
    await init_db()
    
    print("🤖 Starting Maker Bot...")
    await bot.start()
    
    print("⚡ Launching user selfbots...")
    await launch_selfs()
    
    print("🚀 TeleBotCraft is online and fully functional on Railway!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
