# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd

MEOW_STATE = {"run": False}

async def meow_worker(client: Client, chat_id: int):
    MEOW_STATE["run"] = True
    while MEOW_STATE["run"]:
        try:
            await client.send_message(chat_id, "میو")
            await asyncio.sleep(302)
        except Exception:
            await asyncio.sleep(60)

@Client.on_message(self_cmd(["میو روشن"]))
async def meow_on(client: Client, message: Message):
    if not MEOW_STATE["run"]:
        asyncio.create_task(meow_worker(client, message.chat.id))
        await message.edit_text("🐱 بازی میو با تشخیص خودکار تایم فعال شد!")
    else:
        await message.edit_text("⚠️ در حال اجراست.")

@Client.on_message(self_cmd(["میو خاموش"]))
async def meow_off(client: Client, message: Message):
    MEOW_STATE["run"] = False
    await message.edit_text("🛑 ربات میو خاموش شد.")
