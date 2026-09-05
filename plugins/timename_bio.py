# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime
import pytz
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd

FONTS = {
    1: {"0": "𝟎", "1": "𝟏", "2": "𝟐", "3": "𝟑", "4": "𝟒", "5": "𝟓", "6": "𝟔", "7": "𝟕", "8": "𝟖", "9": "𝟗"},
    2: {"0": "𝟘", "1": "𝟙", "2": "𝟚", "3": "𝟛", "4": "𝟜", "5": "𝟝", "6": "𝟞", "7": "𝟟", "8": "𝟠", "9": "𝟡"},
    3: {"0": "⓪", "1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤", "6": "⑥", "7": "⑦", "8": "⑧", "9": "⑨"}
}
timename_active = False

async def time_worker(client: Client, name_prefix: str, font_id: int):
    global timename_active
    timename_active = True
    tz = pytz.timezone("Asia/Tehran")
    last_t = ""
    while timename_active:
        now_t = datetime.now(tz).strftime("%H:%M")
        if now_t != last_t:
            last_t = now_t
            font = FONTS.get(font_id, FONTS[1])
            styled = "".join(font.get(c, c) for c in now_t)
            try:
                await client.update_profile(first_name=f"{name_prefix} {styled}")
            except Exception:
                pass
        await asyncio.sleep(15)

@Client.on_message(self_cmd(["timename start", "زمان اسم روشن"]))
async def start_time(client: Client, message: Message):
    global timename_active
    args = message.command_args.split()
    name = args[0] if len(args) > 0 else "Self"
    font = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
    if not timename_active:
        asyncio.create_task(time_worker(client, name, font))
        await message.edit_text(f"🕒 ساعت فعال شد: `{name}` با فونت `{font}`")
    else:
        await message.edit_text("⚠️ ساعت در حال حاضر روشن است.")

@Client.on_message(self_cmd(["timename stop", "زمان اسم خاموش"]))
async def stop_time(client: Client, message: Message):
    global timename_active
    timename_active = False
    await message.edit_text("🛑 ساعت خاموش شد.")
