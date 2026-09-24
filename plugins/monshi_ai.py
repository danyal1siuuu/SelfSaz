# -*- coding: utf-8 -*-
"""Smart assistant, AI secretary, away mode and AI text tools."""
from __future__ import annotations

import asyncio
import time
import aiosqlite
from pyrogram import Client, filters
from pyrogram.types import Message
from core.filters import self_cmd
from core.plans import has_feature
from core.ai_service import ask_ai
from core.system_settings import get_setting
from config import DB_NAME


def _settings(client):
    return getattr(client, "settings", {}) or {}


async def _stat(user_id: int, field: str) -> None:
    allowed = {"incoming", "outgoing", "ai_replies", "auto_replies"}
    if field not in allowed:
        return
    now = int(time.time())
    col = "last_incoming_at" if field == "incoming" else "last_outgoing_at" if field == "outgoing" else None
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO message_stats(user_id) VALUES (?)", (user_id,))
        await db.execute(f"UPDATE message_stats SET {field}=COALESCE({field},0)+1" + (f", {col}=?" if col else "") + " WHERE user_id=?", ((now, user_id) if col else (user_id,)))
        await db.commit()


@Client.on_message(filters.incoming & filters.private & ~filters.bot, group=2)
async def smart_incoming(client: Client, message: Message):
    if not message.from_user:
        return
    owner_id = getattr(client.me, "id", None)
    if not owner_id:
        return
    settings = _settings(client)
    try:
        await _stat(owner_id, "incoming")
    except Exception:
        pass

    # Auto-read
    if settings.get("auto_read_active", False):
        try:
            await client.read_chat_history(message.chat.id, max_id=message.id)
        except Exception:
            pass

    # Friends are not interrupted by automation unless explicitly enabled.
    if message.from_user.id in getattr(client, "friends_set", set()):
        return

    global_enabled = await get_setting("smart_global_enabled", "1") == "1"
    if not global_enabled:
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        return

    # Fixed auto reply
    if settings.get("auto_reply_active", False):
        cooldown = int(settings.get("auto_reply_cooldown", 30) or 30)
        cache = getattr(client, "auto_reply_users", {})
        now = time.time()
        if now - cache.get(message.from_user.id, 0) >= cooldown:
            cache[message.from_user.id] = now
            client.auto_reply_users = cache
            response = settings.get("auto_reply_text") or await get_setting("smart_default_autoreply", "پیام شما دریافت شد. 🙏")
            try:
                await message.reply_text(response[:3500])
                await _stat(owner_id, "auto_replies")
            except Exception:
                pass
            return

    # AI secretary / away mode
    monshi = bool(getattr(client, "monshi_active", False))
    away = bool(settings.get("away_active", False))
    if not (monshi or away):
        return
    if not await has_feature(owner_id, "ai_monshi"):
        return
    ai_global = await get_setting("smart_ai_global", "1") == "1"
    if not ai_global:
        return

    cooldown = int(settings.get("monshi_cooldown", await get_setting("smart_ai_cooldown", "10")) or 10)
    cache = getattr(client, "monshi_replied_users", {})
    now = time.time()
    if now - cache.get(message.from_user.id, 0) < cooldown:
        return
    cache[message.from_user.id] = now
    client.monshi_replied_users = cache

    system = settings.get("monshi_prompt") or None
    if away and settings.get("away_text"):
        system = (system or "") + "\nحالت مشغول فعال است. " + str(settings.get("away_text"))
    answer, error = await ask_ai(owner_id, text, system_prompt=system, remember=bool(settings.get("ai_memory", True)))
    if not answer:
        fallback = settings.get("away_text") if away else settings.get("monshi_custom_text")
        if not fallback:
            fallback = "سلام! پیامت رسید. فعلاً در دسترس نیستم و به محض فرصت پاسخ می‌دهم. 🙏"
        answer = fallback
    try:
        await message.reply_text(f"🤖 **دستیار هوشمند**\n\n{answer[:3800]}")
        await _stat(owner_id, "ai_replies")
    except Exception:
        pass


@Client.on_message(self_cmd(["ai", "هوش", "دستیار"]))
async def ai_command(client: Client, message: Message):
    prompt = message.command_args.strip()
    if not prompt and message.reply_to_message:
        prompt = message.reply_to_message.text or message.reply_to_message.caption or ""
    if not prompt:
        return await message.edit_text("🤖 نمونه: `.هوش برای معرفی کوتاه محصول من یک متن بنویس`")
    await message.edit_text("⏳ در حال فکر کردن...")
    answer, error = await ask_ai(client.me.id, prompt, remember=True)
    if not answer:
        return await message.edit_text(f"❌ {error}")
    await message.edit_text(f"🤖 **پاسخ هوش مصنوعی**\n\n{answer[:3900]}")


@Client.on_message(self_cmd(["خلاصه", "summarize"]))
async def ai_summarize(client: Client, message: Message):
    text = (message.reply_to_message.text or message.reply_to_message.caption) if message.reply_to_message else ""
    if not text:
        return await message.edit_text("❌ روی متن موردنظر ریپلای کن و `.خلاصه` بزن.")
    await message.edit_text("⏳ در حال خلاصه‌سازی...")
    answer, error = await ask_ai(client.me.id, f"این متن را به فارسی و در چند نکته کوتاه خلاصه کن:\n\n{text}", remember=False)
    return await message.edit_text(f"🧾 **خلاصه**\n\n{answer[:3900] if answer else '❌ '+error}")


@Client.on_message(self_cmd(["ترجمه", "translate"]))
async def ai_translate(client: Client, message: Message):
    target = message.command_args.strip() or "انگلیسی"
    text = (message.reply_to_message.text or message.reply_to_message.caption) if message.reply_to_message else ""
    if not text:
        return await message.edit_text("❌ روی متن ریپلای کن. نمونه: `.ترجمه انگلیسی`")
    await message.edit_text("⏳ در حال ترجمه...")
    prompt = f"متن زیر را به زبان {target} ترجمه کن. فقط ترجمه را بده، بدون توضیح اضافی:\n\n{text}"
    answer, error = await ask_ai(client.me.id, prompt, remember=False)
    return await message.edit_text(answer[:3900] if answer else f"❌ {error}")


@Client.on_message(self_cmd(["یادداشت", "note"]))
async def add_note(client: Client, message: Message):
    note = message.command_args.strip()
    if not note and message.reply_to_message:
        note = message.reply_to_message.text or message.reply_to_message.caption or ""
    if not note:
        return await message.edit_text("📝 نمونه: `.یادداشت خرید دامنه` یا روی یک پیام ریپلای کن.")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO user_notes(owner_id,note) VALUES(?,?)", (client.me.id, note[:4000]))
        await db.commit()
    await message.edit_text("✅ یادداشت ذخیره شد.")


@Client.on_message(self_cmd(["یادداشت‌ها", "notes"]))
async def list_notes(client: Client, message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        rows = await (await db.execute("SELECT id,note FROM user_notes WHERE owner_id=? ORDER BY id DESC LIMIT 20", (client.me.id,))).fetchall()
    if not rows:
        return await message.edit_text("📝 هنوز یادداشتی نداری.")
    text = "📝 **یادداشت‌های من**\n\n" + "\n".join(f"#{i} — {n[:180]}" for i,n in rows)
    await message.edit_text(text[:3900])


@Client.on_message(self_cmd(["حذف یادداشت‌ها", "clear_notes"]))
async def clear_notes(client: Client, message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("DELETE FROM user_notes WHERE owner_id=?", (client.me.id,))
        await db.commit()
    await message.edit_text(f"🗑 {cur.rowcount} یادداشت حذف شد.")


@Client.on_message(filters.me & filters.text, group=9)
async def track_outgoing(client: Client, message: Message):
    try:
        await _stat(client.me.id, "outgoing")
    except Exception:
        pass
