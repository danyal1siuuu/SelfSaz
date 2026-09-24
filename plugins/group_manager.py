# -*- coding: utf-8 -*-
from pyrogram import Client, filters
from pyrogram.types import Message
from core.filters import self_cmd

LOCK_LINKS = set()

@Client.on_message(self_cmd(["قفل لینک"]))
async def lock_links_handler(client: Client, message: Message):
    LOCK_LINKS.add(message.chat.id)
    await message.edit_text("🔒 ارسال لینک در گروه قفل شد.")

@Client.on_message(self_cmd(["بازکردن لینک"]))
async def unlock_links_handler(client: Client, message: Message):
    LOCK_LINKS.discard(message.chat.id)
    await message.edit_text("🔓 قفل لینک باز شد.")

@Client.on_message(filters.group & ~filters.me)
async def enforce_locks(client: Client, message: Message):
    if message.chat.id in LOCK_LINKS and message.text:
        if "t.me/" in message.text or "http://" in message.text or "https://" in message.text:
            try:
                await message.delete()
            except Exception:
                pass
