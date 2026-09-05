# -*- coding: utf-8 -*-
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN, DB_NAME
import aiosqlite

bot = Client("SelfSazHost", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡️ ساخت سلف در چند ثانیه", callback_data="make")],
        [InlineKeyboardButton("📢 کانال رسمی", url="https://t.me/TeleBotCraft")]
    ])
    await message.reply_text("👑 **به سامانه سلف‌ساز جامع TeleBotCraft خوش آمدید!**\nبرای راه‌اندازی سلف روی دکمه زیر کلیک کنید:", reply_markup=kb)

@bot.on_callback_query(filters.regex("make"))
async def make_cb(client: Client, q):
    await q.message.edit_text("📱 لطفاً **String Session** اکانت خود را در این چت ارسال نمایید:")

@bot.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_session(client: Client, message: Message):
    sess = message.text.strip()
    if len(sess) < 50:
        return await message.reply_text("❌ استرینگ سشن ارسالی نامعتبر است.")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, session_string) VALUES (?, ?)", (message.from_user.id, sess))
        await db.commit()
    await message.reply_text("✅ سلف شما فعال شد!\nکافیست در Saved Messages اکانت خود دستور `.راهنما` را تست کنید.")
