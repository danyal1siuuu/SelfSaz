# -*- coding: utf-8 -*-
"""Account-level automations: persistent, rank-limited, actually acting on the Telegram account."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime

import aiosqlite
import pytz
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
from pyrogram.types import Message

from config import DB_NAME
from core.filters import self_cmd
from core.plans import (
    get_automation_react_limit, get_automation_save_limit,
    get_automation_greet_limit, get_automation_name_count,
    get_automation_bio_count, get_automation_interval,
    get_plan_config, get_user_profile,
)


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


async def _read_settings(user_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        row = await (await db.execute("SELECT settings FROM users WHERE user_id=?", (user_id,))).fetchone()
    try:
        return json.loads(row[0]) if row and row[0] else {}
    except Exception:
        return {}


async def _save_settings(user_id: int, patch: dict) -> dict:
    st = await _read_settings(user_id)
    st.update(patch)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET settings=? WHERE user_id=?", (json.dumps(st, ensure_ascii=False), user_id))
        await db.commit()
    return st


async def _usage(client, key: str, limit: int) -> bool:
    """Return True and increment today's usage when under the rank limit."""
    if limit <= 0:
        return False
    settings = getattr(client, "settings", {}) or {}
    usage = dict(settings.get("automation_usage") or {})
    today = _today()
    bucket = dict(usage.get(today) or {})
    used = int(bucket.get(key, 0) or 0)
    if used >= limit:
        return False
    bucket[key] = used + 1
    # Keep only today + previous day to prevent settings bloat.
    usage = {k: v for k, v in usage.items() if k in {today, time.strftime("%Y-%m-%d", time.localtime(time.time()-86400))}}
    usage[today] = bucket
    st = await _save_settings(client.me.id, {"automation_usage": usage})
    client.settings = st
    return True


async def _cycle_worker(client, kind: str):
    last_index = -1
    while getattr(client, f"auto_{kind}_active", False):
        try:
            uid = client.me.id
            st = await _read_settings(uid)
            values = list(st.get(f"automation_{kind}_list") or [])
            if not values:
                # Safe defaults so turning the feature on produces visible behaviour immediately.
                if kind == "name":
                    base = getattr(client, "automation_original_name", None) or client.me.first_name or "Self"
                    values = [base, f"{base} ✦", f"{base} •"]
                else:
                    values = ["🟢 آنلاین و آماده پاسخ", "⚡ فعال با SelfSaz", "✨ یک روز خوب داشته باشی"]
            max_count = await (get_automation_name_count(uid) if kind == "name" else get_automation_bio_count(uid))
            values = values[:max_count]
            if not values:
                values = [client.me.first_name or "Self"] if kind == "name" else ["SelfSaz"]
            last_index = (last_index + 1) % len(values)
            value = str(values[last_index]).strip()[:64 if kind == "name" else 70]
            if kind == "name":
                await client.update_profile(first_name=value)
            else:
                await client.update_profile(bio=value)
        except Exception:
            pass
        await asyncio.sleep(await get_automation_interval(client.me.id))


async def start_account_automations(client):
    """Start persisted account automations after the selfbot connects."""
    settings = getattr(client, "settings", {}) or {}
    client.automation_original_name = settings.get("automation_original_name") or getattr(client, "original_name", None) or client.me.first_name
    client.auto_name_active = bool(settings.get("automation_name_active", False))
    client.auto_bio_active = bool(settings.get("automation_bio_active", False))
    client.auto_name_task = None
    client.auto_bio_task = None
    if client.auto_name_active:
        client.auto_name_task = asyncio.create_task(_cycle_worker(client, "name"))
    if client.auto_bio_active:
        client.auto_bio_task = asyncio.create_task(_cycle_worker(client, "bio"))


async def stop_account_automations(client):
    for attr in ("auto_name_active", "auto_bio_active"):
        setattr(client, attr, False)
    for attr in ("auto_name_task", "auto_bio_task"):
        task = getattr(client, attr, None)
        if task:
            task.cancel()
            setattr(client, attr, None)
    try:
        orig_name = getattr(client, "automation_original_name", None) or getattr(client, "original_name", None)
        if orig_name:
            await client.update_profile(first_name=orig_name[:64])
    except Exception:
        pass


@Client.on_message(self_cmd(["اتوماسیون وضعیت", "automation status"]))
async def automation_status(client: Client, message: Message):
    st = await _read_settings(client.me.id)
    p = await get_user_profile(client.me.id) or {"plan": "normal"}
    cfg = get_plan_config(p["plan"])
    await message.edit_text(
        "⚙️ **اتوماسیون واقعی حساب**\n\n"
        f"🪪 چرخش نام: {'روشن ✅' if st.get('automation_name_active') else 'خاموش ❌'}\n"
        f"📝 چرخش Bio: {'روشن ✅' if st.get('automation_bio_active') else 'خاموش ❌'}\n"
        f"💾 ذخیره خودکار پیام: {'روشن ✅' if st.get('automation_save_active') else 'خاموش ❌'}\n"
        f"❤️ واکنش خودکار: {'روشن ✅' if st.get('automation_react_active') else 'خاموش ❌'}\n"
        f"👋 خوش‌آمد خودکار: {'روشن ✅' if st.get('automation_greet_active') else 'خاموش ❌'}\n"
        f"⌨️ تایپ خودکار: {'روشن ✅' if st.get('automation_typing_active') else 'خاموش ❌'}\n\n"
        f"رنک: {cfg['badge']} {cfg['title']}"
    )


@Client.on_message(self_cmd(["اتوماسیون نام روشن"]))
async def name_on(client: Client, message: Message):
    limit = await get_automation_name_count(client.me.id)
    st = await _save_settings(client.me.id, {"automation_name_active": True, "automation_original_name": getattr(client, "automation_original_name", None) or getattr(client, "original_name", None) or client.me.first_name})
    client.settings = st; client.automation_original_name = st.get("automation_original_name")
    client.auto_name_active = True
    if getattr(client, "auto_name_task", None): client.auto_name_task.cancel()
    client.auto_name_task = asyncio.create_task(_cycle_worker(client, "name"))
    await message.edit_text(f"🪪 چرخش خودکار نام روشن شد. حداکثر {limit} نام از لیست تنظیم‌شده استفاده می‌شود.")


@Client.on_message(self_cmd(["اتوماسیون نام خاموش"]))
async def name_off(client: Client, message: Message):
    client.auto_name_active = False
    if getattr(client, "auto_name_task", None): client.auto_name_task.cancel(); client.auto_name_task = None
    orig = getattr(client, "automation_original_name", None) or getattr(client, "original_name", None)
    if orig:
        try: await client.update_profile(first_name=orig[:64])
        except Exception: pass
    await _save_settings(client.me.id, {"automation_name_active": False})
    await message.edit_text("🪪 چرخش خودکار نام خاموش شد و نام اصلی بازگردانده شد.")


@Client.on_message(self_cmd(["اتوماسیون bio روشن", "اتوماسیون بایو روشن"]))
async def bio_on(client: Client, message: Message):
    limit = await get_automation_bio_count(client.me.id)
    st = await _save_settings(client.me.id, {"automation_bio_active": True})
    client.settings = st; client.auto_bio_active = True
    if getattr(client, "auto_bio_task", None): client.auto_bio_task.cancel()
    client.auto_bio_task = asyncio.create_task(_cycle_worker(client, "bio"))
    await message.edit_text(f"📝 چرخش خودکار Bio روشن شد. حداکثر {limit} متن از لیست Bio استفاده می‌شود.")


@Client.on_message(self_cmd(["اتوماسیون bio خاموش", "اتوماسیون بایو خاموش"]))
async def bio_off(client: Client, message: Message):
    client.auto_bio_active = False
    if getattr(client, "auto_bio_task", None): client.auto_bio_task.cancel(); client.auto_bio_task = None
    await _save_settings(client.me.id, {"automation_bio_active": False})
    await message.edit_text("📝 چرخش خودکار Bio خاموش شد.")


@Client.on_message(self_cmd(["اتوماسیون نام‌ها"]))
async def set_names(client: Client, message: Message):
    raw = (getattr(message, "command_args", "") or "").strip()
    values = [x.strip() for x in raw.split("|") if x.strip()]
    limit = await get_automation_name_count(client.me.id)
    if not values:
        return await message.edit_text(f"🪪 نام‌ها را با `|` جدا کن. حداکثر {limit} مورد در رنک شما مجاز است.\nمثال: `.اتوماسیون نام‌ها دانیال | دانیال ✦ | دانیال •`")
    values = values[:limit]
    st = await _save_settings(client.me.id, {"automation_name_list": values}); client.settings = st
    await message.edit_text(f"✅ {len(values)} نام برای چرخه خودکار ذخیره شد. سقف رنک: {limit}.")

@Client.on_message(self_cmd(["اتوماسیون bioها", "اتوماسیون بایوها"]))
async def set_bios(client: Client, message: Message):
    raw = (getattr(message, "command_args", "") or "").strip()
    values = [x.strip() for x in raw.split("|") if x.strip()]
    limit = await get_automation_bio_count(client.me.id)
    if not values:
        return await message.edit_text(f"📝 متن‌های Bio را با `|` جدا کن. حداکثر {limit} مورد در رنک شما مجاز است.\nمثال: `.اتوماسیون بایوها آنلاین 🟢 | در حال کار ⚡ | بعداً پاسخ می‌دهم ✨`")
    values = values[:limit]
    st = await _save_settings(client.me.id, {"automation_bio_list": values}); client.settings = st
    await message.edit_text(f"✅ {len(values)} متن Bio برای چرخه خودکار ذخیره شد. سقف رنک: {limit}.")

@Client.on_message(filters.private & ~filters.me & filters.incoming)
async def incoming_account_automation(client: Client, message: Message):
    uid = client.me.id
    settings = getattr(client, "settings", {}) or {}
    # Auto-save: copy incoming private messages to Saved Messages.
    if settings.get("automation_save_active") and message.from_user and not message.from_user.is_bot:
        limit = await get_automation_save_limit(uid)
        if await _usage(client, "save", limit):
            try:
                await message.copy("me")
            except Exception:
                pass
    # Auto-reaction: explicit account action, rank-limited daily.
    if settings.get("automation_react_active") and message.from_user and not message.from_user.is_bot:
        limit = await get_automation_react_limit(uid)
        if await _usage(client, "react", limit):
            try:
                emoji = str(settings.get("automation_react_emoji") or "❤️")[:2]
                await message.react(emoji)
            except Exception:
                pass
    # Greeting: once per sender per day.
    if settings.get("automation_greet_active") and message.from_user and not message.from_user.is_bot:
        limit = await get_automation_greet_limit(uid)
        greeted = set(settings.get("automation_greeted_today") or [])
        key = f"{_today()}:{message.from_user.id}"
        if key not in greeted and await _usage(client, "greet", limit):
            greeted.add(key)
            greeted = set(list(greeted)[-max(10, limit * 2):])
            await _save_settings(uid, {"automation_greeted_today": list(greeted)})
            try:
                await message.reply_text(settings.get("automation_greet_text") or "سلام 👋 پیام شما دریافت شد؛ به‌زودی پاسخ می‌دهم.")
            except Exception:
                pass
    # Typing indicator makes the existing automatic assistant feel active.
    if settings.get("automation_typing_active") and message.from_user and not message.from_user.is_bot:
        try:
            await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        except Exception:
            pass


@Client.on_message(self_cmd(["اتوماسیون ذخیره روشن"]))
async def save_on(client: Client, message: Message):
    st = await _save_settings(client.me.id, {"automation_save_active": True}); client.settings = st
    await message.edit_text(f"💾 ذخیره خودکار پیام‌های خصوصی روشن شد. سقف روزانه رنک شما: {await get_automation_save_limit(client.me.id)} پیام.")

@Client.on_message(self_cmd(["اتوماسیون ذخیره خاموش"]))
async def save_off(client: Client, message: Message):
    st = await _save_settings(client.me.id, {"automation_save_active": False}); client.settings = st
    await message.edit_text("💾 ذخیره خودکار خاموش شد.")

@Client.on_message(self_cmd(["اتوماسیون واکنش روشن"]))
async def react_on(client: Client, message: Message):
    limit = await get_automation_react_limit(client.me.id)
    if limit <= 0:
        return await message.edit_text("🔒 واکنش خودکار از رنک آهنی فعال می‌شود.")
    st = await _save_settings(client.me.id, {"automation_react_active": True}); client.settings = st
    await message.edit_text(f"❤️ واکنش خودکار روشن شد. سقف روزانه: {limit} پیام.\nایموجی فعلی: {st.get('automation_react_emoji','❤️')}")

@Client.on_message(self_cmd(["اتوماسیون واکنش خاموش"]))
async def react_off(client: Client, message: Message):
    st = await _save_settings(client.me.id, {"automation_react_active": False}); client.settings = st
    await message.edit_text("❤️ واکنش خودکار خاموش شد.")

@Client.on_message(self_cmd(["اتوماسیون خوشامد روشن"]))
async def greet_on(client: Client, message: Message):
    st = await _save_settings(client.me.id, {"automation_greet_active": True}); client.settings = st
    await message.edit_text(f"👋 خوش‌آمد خودکار روشن شد. سقف روزانه: {await get_automation_greet_limit(client.me.id)} نفر.")

@Client.on_message(self_cmd(["اتوماسیون خوشامد خاموش"]))
async def greet_off(client: Client, message: Message):
    st = await _save_settings(client.me.id, {"automation_greet_active": False}); client.settings = st
    await message.edit_text("👋 خوش‌آمد خودکار خاموش شد.")

@Client.on_message(self_cmd(["اتوماسیون تایپ روشن"]))
async def typing_on(client: Client, message: Message):
    st = await _save_settings(client.me.id, {"automation_typing_active": True}); client.settings = st
    await message.edit_text("⌨️ تایپ خودکار هنگام دریافت پیام روشن شد.")

@Client.on_message(self_cmd(["اتوماسیون تایپ خاموش"]))
async def typing_off(client: Client, message: Message):
    st = await _save_settings(client.me.id, {"automation_typing_active": False}); client.settings = st
    await message.edit_text("⌨️ تایپ خودکار خاموش شد.")

@Client.on_message(self_cmd(["اتوماسیون ایموجی"]))
async def set_react_emoji(client: Client, message: Message):
    emoji = (getattr(message, "command_args", "") or "").strip()
    if not emoji:
        return await message.edit_text("❤️ بعد از دستور یک ایموجی بفرست. مثال: `.اتوماسیون ایموجی 🔥`")
    st = await _save_settings(client.me.id, {"automation_react_emoji": emoji[:4]}); client.settings = st
    await message.edit_text(f"✅ ایموجی واکنش خودکار تنظیم شد: {emoji[:4]}")

@Client.on_message(self_cmd(["اتوماسیون پیام خوشامد"]))
async def set_greet_text(client: Client, message: Message):
    txt = (getattr(message, "command_args", "") or "").strip()
    if not txt:
        return await message.edit_text("👋 متن خوش‌آمد را بعد از دستور بنویس. مثال: `.اتوماسیون پیام خوشامد سلام 👋`")
    st = await _save_settings(client.me.id, {"automation_greet_text": txt[:500]}); client.settings = st
    await message.edit_text("✅ متن خوش‌آمد خودکار ذخیره شد.")
