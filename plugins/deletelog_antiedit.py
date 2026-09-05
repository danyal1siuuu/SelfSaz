# -*- coding: utf-8 -*-
from pyrogram import Client, filters
from pyrogram.types import Message

MSG_STORE = {}

@Client.on_message(filters.incoming, group=1)
async def store_msg(client: Client, message: Message):
    if message.text or message.caption:
        cid = message.chat.id
        if cid not in MSG_STORE:
            MSG_STORE[cid] = {}
        MSG_STORE[cid][message.id] = {
            "text": message.text or message.caption,
            "sender": message.from_user.mention if message.from_user else "ناشناس"
        }
    message.continue_propagation()

@Client.on_deleted_messages()
async def del_tracker(client: Client, messages: list[Message]):
    for msg in messages:
        cid = msg.chat.id if msg.chat else None
        if cid and cid in MSG_STORE and msg.id in MSG_STORE[cid]:
            info = MSG_STORE[cid][msg.id]
            alert = f"🚨 **پیام حذف شد!**\n👤 فرستنده: {info['sender']}\n📝 متن: `{info['text']}`"
            try:
                await client.send_message("me", alert)
            except Exception:
                pass
            del MSG_STORE[cid][msg.id]

@Client.on_edited_message(filters.incoming)
async def edit_tracker(client: Client, message: Message):
    cid = message.chat.id
    if cid in MSG_STORE and message.id in MSG_STORE[cid]:
        old = MSG_STORE[cid][message.id]["text"]
        new = message.text or message.caption or ""
        if old != new:
            alert = f"✏️ **پیام ادیت شد!**\n👤 فرستنده: {message.from_user.mention if message.from_user else 'ناشناس'}\n🔴 قبلی: `{old}`\n🟢 جدید: `{new}`"
            try:
                await client.send_message("me", alert)
            except Exception:
                pass
            MSG_STORE[cid][message.id]["text"] = new
