# -*- coding: utf-8 -*-
import random
import aiosqlite
from pyrogram import Client, filters
from pyrogram.types import Message
from core.filters import self_cmd
from config import DB_NAME

ENEMY_PHRASES = ["در حد ما نیستی کوچولو 🍼", "نمی‌شنوم صداتو ضعیفی!", "برو بزرگترت بیاد!"]
FRIEND_PHRASES = ["سلام تاج سرم ❤️", "همیشه جات تو قلبمونه رفیق ✨", "عزیزی برامون 👑"]

@Client.on_message(self_cmd(["addenemy", "افزودن دشمن"]))
async def add_enemy(client: Client, message: Message):
    target = message.reply_to_message.from_user.id if message.reply_to_message else None
    if not target:
        return await message.edit_text("❌ روی پیام کاربر ریپلای کنید.")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO relations (owner_id, target_id, type) VALUES (?, ?, 'enemy')", (client.me.id, target))
        await db.commit()
    await message.edit_text(f"🛡 کاربر `{target}` به لیست دشمنان اضافه شد.")

@Client.on_message(self_cmd(["addfriend", "افزودن دوست"]))
async def add_friend(client: Client, message: Message):
    target = message.reply_to_message.from_user.id if message.reply_to_message else None
    if not target:
        return await message.edit_text("❌ روی پیام کاربر ریپلای کنید.")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO relations (owner_id, target_id, type) VALUES (?, ?, 'friend')", (client.me.id, target))
        await db.commit()
    await message.edit_text(f"❤️ کاربر `{target}` به لیست دوستان ویژه اضافه شد.")

@Client.on_message(self_cmd(["clearenemy", "پاکسازی دشمن"]))
async def clear_enemy(client: Client, message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM relations WHERE owner_id = ? AND type = 'enemy'", (client.me.id,))
        await db.commit()
    await message.edit_text("🗑 لیست دشمنان کاملاً پاک شد.")

@Client.on_message(filters.incoming & ~filters.bot)
async def relation_auto_reply(client: Client, message: Message):
    if not message.from_user:
        return
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT type FROM relations WHERE owner_id = ? AND target_id = ?", (client.me.id, message.from_user.id))
        row = await cursor.fetchone()
    if row:
        if row[0] == "enemy":
            await message.reply_text(random.choice(ENEMY_PHRASES))
        elif row[0] == "friend":
            await message.reply_text(random.choice(FRIEND_PHRASES))
