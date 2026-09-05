# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.me)
async def auto_clean_runner(client: Client, message: Message):
    if not getattr(client, "cleaner_active", False):
        return
    delay = getattr(client, "cleaner_delay", 20)
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass
