# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from core.plans import get_cleaner_min_delay

@Client.on_message(filters.me)
async def auto_clean_runner(client: Client, message: Message):
    if not getattr(client, "cleaner_active", False):
        return
    configured = int(getattr(client, "cleaner_delay", 20) or 20)
    try:
        minimum = await get_cleaner_min_delay(client.me.id)
    except Exception:
        minimum = configured
    await asyncio.sleep(max(configured, minimum))
    try:
        await message.delete()
    except Exception:
        pass
