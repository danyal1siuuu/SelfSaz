# -*- coding: utf-8 -*-
import random
import aiosqlite
from pyrogram import Client, filters
from pyrogram.types import Message
from core.filters import self_cmd
from core.plans import get_relation_limit
from config import DB_NAME

ENEMY_PHRASES = ["در حد ما نیستی کوچولو 🍼", "نمی‌شنوم صداتو ضعیفی!", "برو بزرگترت بیاد!"]
FRIEND_PHRASES = ["سلام تاج سرم ❤️", "همیشه جات تو قلبمونه رفیق ✨", "عزیزی برامون 👑"]

async def _add_relation(client: Client, message: Message, relation_type: str):
    target = message.reply_to_message.from_user.id if message.reply_to_message and message.reply_to_message.from_user else None
    if not target:
        return await message.edit_text("❌ روی پیام کاربر ریپلای کنید.")
    owner = client.me.id
    async with aiosqlite.connect(DB_NAME) as db:
        count = (await (await db.execute("SELECT COUNT(*) FROM relations WHERE owner_id = ? AND type = ?", (owner, relation_type))).fetchone())[0]
        exists = await (await db.execute("SELECT 1 FROM relations WHERE owner_id = ? AND target_id = ? AND type = ?", (owner, target, relation_type))).fetchone()
        limit = await get_relation_limit(owner, relation_type)
        if not exists and count >= limit:
            label = "دوستان" if relation_type == "friend" else "دشمنان"
            return await message.edit_text(f"🔒 سقف {label} پلن شما `{limit}` نفر است. برای افزایش سقف، پلن را ارتقا دهید.")
        await db.execute("INSERT OR REPLACE INTO relations (owner_id, target_id, type) VALUES (?, ?, ?)", (owner, target, relation_type))
        await db.commit()
    icon = "❤️" if relation_type == "friend" else "⚔️"
    label = "دوستان ویژه" if relation_type == "friend" else "دشمنان"
    await message.edit_text(f"{icon} کاربر `{target}` به لیست {label} اضافه شد.\n📊 سقف پلن: `{limit}` نفر")

@Client.on_message(self_cmd(["addenemy", "افزودن دشمن"]))
async def add_enemy(client: Client, message: Message):
    return await _add_relation(client, message, "enemy")

@Client.on_message(self_cmd(["addfriend", "افزودن دوست"]))
async def add_friend(client: Client, message: Message):
    return await _add_relation(client, message, "friend")

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
        row = await (await db.execute("SELECT type FROM relations WHERE owner_id = ? AND target_id = ?", (client.me.id, message.from_user.id))).fetchone()
    if row:
        if row[0] == "enemy":
            await message.reply_text(random.choice(ENEMY_PHRASES))
        elif row[0] == "friend":
            await message.reply_text(random.choice(FRIEND_PHRASES))
