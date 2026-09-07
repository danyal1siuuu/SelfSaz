# -*- coding: utf-8 -*-
"""Central plan, rank, referral and coin-economy engine for SelfSaz."""
from __future__ import annotations

import time
from typing import Any

import aiosqlite

from config import DB_NAME

PLAN_ORDER = ["normal", "iron", "bronze", "silver", "gold", "diamond"]

# Each higher rank needs both enough coins and enough successful referrals.
PLANS_DATA: dict[str, dict[str, Any]] = {
    "normal": {
        "title": "عادی", "short_title": "عادی", "badge": "👤",
        "price_coins": 0, "required_referrals": 0,
        "max_friends": 3, "max_enemies": 3, "allowed_fonts": [1, 2],
        "min_cleaner_delay": 60, "ai_monshi": False, "anti_delete_logger": False,
        "daily_coins": 5, "activity_coins": 1, "activity_daily_cap": 20,
        "max_yt_mb": 100, "description": "شروع رایگان برای استفاده‌های پایه",
    },
    "iron": {
        "title": "آهنی", "short_title": "آهنی", "badge": "⛓️",
        "price_coins": 500, "required_referrals": 5,
        "max_friends": 5, "max_enemies": 5, "allowed_fonts": [1, 2, 3],
        "min_cleaner_delay": 30, "ai_monshi": False, "anti_delete_logger": True,
        "daily_coins": 10, "activity_coins": 2, "activity_daily_cap": 40,
        "max_yt_mb": 250, "description": "پایه تقویت‌شده با امکانات بیشتر",
    },
    "bronze": {
        "title": "برنزی", "short_title": "برنزی", "badge": "🥉",
        "price_coins": 1500, "required_referrals": 15,
        "max_friends": 15, "max_enemies": 15, "allowed_fonts": [1, 2, 3, 4, 5],
        "min_cleaner_delay": 20, "ai_monshi": False, "anti_delete_logger": True,
        "daily_coins": 25, "activity_coins": 3, "activity_daily_cap": 80,
        "max_yt_mb": 500, "description": "برای کاربران فعال با سقف‌های بالاتر",
    },
    "silver": {
        "title": "نقره‌ای", "short_title": "نقره‌ای", "badge": "🥈",
        "price_coins": 4000, "required_referrals": 30,
        "max_friends": 40, "max_enemies": 40, "allowed_fonts": list(range(1, 8)),
        "min_cleaner_delay": 10, "ai_monshi": True, "anti_delete_logger": True,
        "daily_coins": 50, "activity_coins": 4, "activity_daily_cap": 150,
        "max_yt_mb": 1024, "description": "سطح نیمه‌حرفه‌ای با منشی هوشمند",
    },
    "gold": {
        "title": "طلایی", "short_title": "طلایی", "badge": "🥇",
        "price_coins": 10000, "required_referrals": 60,
        "max_friends": 100, "max_enemies": 100, "allowed_fonts": list(range(1, 11)),
        "min_cleaner_delay": 5, "ai_monshi": True, "anti_delete_logger": True,
        "daily_coins": 100, "activity_coins": 6, "activity_daily_cap": 300,
        "max_yt_mb": 2048, "description": "سطح حرفه‌ای برای استفاده سنگین",
    },
    "diamond": {
        "title": "الماسی", "short_title": "الماسی", "badge": "💎",
        "price_coins": 25000, "required_referrals": 120,
        "max_friends": 9999, "max_enemies": 9999, "allowed_fonts": list(range(1, 11)),
        "min_cleaner_delay": 1, "ai_monshi": True, "anti_delete_logger": True,
        "daily_coins": 250, "activity_coins": 10, "activity_daily_cap": 600,
        "max_yt_mb": None, "description": "بالاترین سطح؛ بدون سقف پلن برای حجم یوتیوب",
    },
}


def get_plan_config(plan_key: str | None) -> dict[str, Any]:
    return PLANS_DATA.get(plan_key or "normal", PLANS_DATA["normal"])


def normalize_plan(plan_key: str | None, is_vip: int | bool = 0) -> str:
    if is_vip:
        return "diamond"
    return str(plan_key) if plan_key in PLANS_DATA else "normal"


def format_mb(value: int | None) -> str:
    if value is None:
        return "نامحدود"
    if value >= 1024:
        return f"{value / 1024:g} گیگابایت"
    return f"{value} مگابایت"


def create_progress_bar(current: int, total: int, length: int = 12) -> str:
    if total <= 0:
        return "▰" * length
    fraction = min(1.0, max(0.0, current / total))
    filled = int(fraction * length)
    return "▰" * filled + "▱" * (length - filled)


async def get_user_profile(user_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            """SELECT coins, plan, activity_score, last_daily_claim, is_vip,
                      previous_plan, referred_by, referral_count, last_activity_reward,
                      activity_reward_date, activity_reward_coins
               FROM users WHERE user_id = ?""",
            (user_id,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "coins": int(row[0] or 0),
        "plan": normalize_plan(row[1], row[4]),
        "activity_score": int(row[2] or 0),
        "last_daily": int(row[3] or 0),
        "is_vip": bool(row[4]),
        "previous_plan": normalize_plan(row[5], 0),
        "referred_by": int(row[6] or 0) or None,
        "referral_count": int(row[7] or 0),
        "last_activity_reward": int(row[8] or 0),
        "activity_reward_date": row[9] or "",
        "activity_reward_coins": int(row[10] or 0),
    }


async def get_user_yt_limit_mb(user_id: int) -> int | None:
    profile = await get_user_profile(user_id)
    return get_plan_config(profile["plan"] if profile else "normal")["max_yt_mb"]


async def get_user_plan_name(user_id: int) -> str:
    profile = await get_user_profile(user_id)
    return profile["plan"] if profile else "normal"


async def has_feature(user_id: int, feature: str) -> bool:
    profile = await get_user_profile(user_id)
    return bool(get_plan_config(profile["plan"] if profile else "normal").get(feature, False))


async def get_relation_limit(user_id: int, relation_type: str) -> int:
    profile = await get_user_profile(user_id)
    cfg = get_plan_config(profile["plan"] if profile else "normal")
    return int(cfg["max_friends"] if relation_type == "friend" else cfg["max_enemies"])


async def get_cleaner_min_delay(user_id: int) -> int:
    profile = await get_user_profile(user_id)
    return int(get_plan_config(profile["plan"] if profile else "normal")["min_cleaner_delay"])


async def get_allowed_fonts(user_id: int) -> list[int]:
    profile = await get_user_profile(user_id)
    return list(get_plan_config(profile["plan"] if profile else "normal")["allowed_fonts"])


async def add_activity(user_id: int, points: int = 1, bonus_coins: int = 0) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET activity_score = COALESCE(activity_score, 0) + ?, coins = MAX(0, COALESCE(coins, 0) + ?) WHERE user_id = ?",
            (points, bonus_coins, user_id),
        )
        await db.commit()


async def record_activity_reward(user_id: int, points: int = 1) -> tuple[bool, int]:
    """Award activity XP + rank-scaled coins at most once every 10 minutes per user,
    with a daily cap per plan. Returns (awarded, coins_added).
    """
    profile = await get_user_profile(user_id)
    if not profile:
        return False, 0
    cfg = get_plan_config(profile["plan"])
    now = int(time.time())
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    if profile["activity_reward_date"] != today:
        spent_today = 0
    else:
        spent_today = profile["activity_reward_coins"]
    if now - profile["last_activity_reward"] < 600:
        return False, 0
    reward = min(int(cfg["activity_coins"]), max(0, int(cfg["activity_daily_cap"]) - spent_today))
    if reward <= 0:
        return False, 0
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """UPDATE users SET activity_score = COALESCE(activity_score, 0) + ?,
               coins = COALESCE(coins, 0) + ?, last_activity_reward = ?,
               activity_reward_date = ?, activity_reward_coins = ? WHERE user_id = ?""",
            (points, reward, now, today, spent_today + reward, user_id),
        )
        await db.commit()
    return True, reward


async def claim_daily_bonus(user_id: int) -> tuple[bool, str]:
    now = int(time.time())
    profile = await get_user_profile(user_id)
    if not profile:
        return False, "❌ کاربر یافت نشد."
    elapsed = now - profile["last_daily"]
    if elapsed < 86400:
        remain = 86400 - elapsed
        h, rem = divmod(remain, 3600)
        m = rem // 60
        return False, f"⏳ پاداش امروز قبلاً دریافت شده است.\nزمان باقی‌مانده: `{h}` ساعت و `{m}` دقیقه."
    cfg = get_plan_config(profile["plan"])
    reward = int(cfg["daily_coins"])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET coins = COALESCE(coins, 0) + ?, last_daily_claim = ?, activity_score = COALESCE(activity_score, 0) + 5 WHERE user_id = ?",
            (reward, now, user_id),
        )
        await db.commit()
    return True, f"🎁 `{reward}` سکه + `5 XP` دریافت کردی؛ پاداش روزانه {cfg['badge']} {cfg['short_title']} ثبت شد."


async def process_referral(referrer_id: int, referred_id: int) -> tuple[bool, str]:
    if referrer_id == referred_id:
        return False, "self"
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
        if not await cur.fetchone():
            return False, "referrer_missing"
        cur = await db.execute("SELECT referred_by FROM users WHERE user_id = ?", (referred_id,))
        row = await cur.fetchone()
        if not row:
            return False, "referred_missing"
        if row[0]:
            return False, "already_referred"
        cur = await db.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (referred_id,))
        if await cur.fetchone():
            return False, "already_referred"
        reward = 50
        await db.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, referred_id))
        await db.execute("UPDATE users SET referral_count = COALESCE(referral_count, 0) + 1, coins = COALESCE(coins, 0) + ?, activity_score = COALESCE(activity_score, 0) + 25 WHERE user_id = ?", (reward, referrer_id))
        await db.execute("INSERT INTO referrals (referrer_id, referred_id, reward_coins) VALUES (?, ?, ?)", (referrer_id, referred_id, reward))
        await db.commit()
    return True, str(reward)


async def upgrade_user_plan(user_id: int, target_plan: str) -> tuple[bool, str]:
    if target_plan not in PLANS_DATA:
        return False, "❌ پلن نامعتبر است."
    profile = await get_user_profile(user_id)
    if not profile:
        return False, "❌ کاربر یافت نشد."
    current = normalize_plan(profile["plan"])
    current_idx = PLAN_ORDER.index(current)
    target_idx = PLAN_ORDER.index(target_plan)
    if target_idx != current_idx + 1:
        return False, "⚠️ ارتقا باید مرحله‌به‌مرحله انجام شود. ابتدا رنک بعدی را باز کن."
    cfg = PLANS_DATA[target_plan]
    if profile["referral_count"] < cfg["required_referrals"]:
        return False, f"👥 برای رنک **{cfg['title']}** حداقل `{cfg['required_referrals']}` دعوت موفق لازم است. شما `{profile['referral_count']}` دعوت دارید."
    price = int(cfg["price_coins"])
    if profile["coins"] < price:
        return False, f"🪙 سکه کافی نیست.\nنیاز: `{price}` | موجودی: `{profile['coins']}` سکه"
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET coins = coins - ?, plan = ?, is_vip = ? WHERE user_id = ?", (price, target_plan, 1 if target_plan == "diamond" else 0, user_id))
        await db.commit()
    return True, f"🎉 شما به **{cfg['badge']} {cfg['title']}** ارتقا یافتید."


async def admin_set_plan(user_id: int, target_plan: str) -> tuple[bool, str]:
    if target_plan not in PLANS_DATA:
        return False, "❌ رنک نامعتبر است."
    profile = await get_user_profile(user_id)
    if not profile:
        return False, "❌ کاربر یافت نشد."
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET plan = ?, is_vip = ? WHERE user_id = ?", (target_plan, 1 if target_plan == "diamond" else 0, user_id))
        await db.commit()
    cfg = PLANS_DATA[target_plan]
    return True, f"✅ رنک کاربر `{user_id}` روی **{cfg['badge']} {cfg['title']}** تنظیم شد."


async def set_admin_vip(user_id: int, enabled: bool) -> tuple[bool, str]:
    profile = await get_user_profile(user_id)
    if not profile:
        return False, "❌ کاربر یافت نشد."
    return await admin_set_plan(user_id, "diamond" if enabled else "normal")


def render_plan_dashboard(profile: dict[str, Any]) -> str:
    plan_key = normalize_plan(profile.get("plan"), profile.get("is_vip", 0))
    cfg = get_plan_config(plan_key)
    idx = PLAN_ORDER.index(plan_key)
    if idx < len(PLAN_ORDER) - 1:
        next_key = PLAN_ORDER[idx + 1]
        next_cfg = PLANS_DATA[next_key]
        coin_need = max(0, next_cfg["price_coins"] - profile["coins"])
        ref_need = max(0, next_cfg["required_referrals"] - profile["referral_count"])
        progress_text = f"🪙 سکه تا رنک بعدی: `{coin_need}`\n👥 دعوت باقی‌مانده: `{ref_need}`"
        next_text = f"{next_cfg['badge']} {next_cfg['title']}"
    else:
        next_text = "👑 حداکثر سطح"
        progress_text = "✅ بالاترین رنک فعال است"
    return (
        "👑 **مرکز رنک و اقتصاد سلف‌ساز**\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 رنک فعلی: **{cfg['badge']} {cfg['title']}**\n"
        f"🪙 موجودی: `{profile['coins']}` سکه\n"
        f"⚡ XP فعالیت: `{profile['activity_score']}`\n"
        f"👥 دعوت موفق: `{profile['referral_count']}`\n"
        f"📈 رنک بعدی: **{next_text}**\n{progress_text}\n\n"
        "📋 **دسترسی‌های رنک**\n"
        f"📹 یوتیوب: `{format_mb(cfg['max_yt_mb'])}`\n"
        f"❤️ دوستان: `{cfg['max_friends']}` | ⚔️ دشمنان: `{cfg['max_enemies']}`\n"
        f"⏰ حداقل تایمر: `{cfg['min_cleaner_delay']} ثانیه`\n"
        f"🔤 فونت: `{len(cfg['allowed_fonts'])}/10`\n"
        f"🤖 منشی: `{'فعال ✅' if cfg['ai_monshi'] else 'قفل 🔒'}`\n"
        f"🛡 لاگر: `{'فعال ✅' if cfg['anti_delete_logger'] else 'قفل 🔒'}`\n"
        f"🎁 پاداش روزانه: `{cfg['daily_coins']}` سکه\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


def render_plans_catalog(profile: dict[str, Any]) -> str:
    current = normalize_plan(profile.get("plan"), profile.get("is_vip", 0))
    lines = ["🛍 **فروشگاه رنک‌های سلف‌ساز**", "━━━━━━━━━━━━━━━━━━━━", "برای ارتقا باید هم سکه کافی داشته باشید و هم دعوت موفق موردنیاز همان رنک را کامل کنید.", ""]
    for key in PLAN_ORDER:
        cfg = PLANS_DATA[key]
        marker = "✅ رنک فعلی" if key == current else f"🪙 {cfg['price_coins']} سکه | 👥 {cfg['required_referrals']} دعوت"
        lines.append(f"{cfg['badge']} **{cfg['title']}** — {marker}\n   📹 {format_mb(cfg['max_yt_mb'])} | ❤️ {cfg['max_friends']} | ⚔️ {cfg['max_enemies']} | 🎁 {cfg['daily_coins']} سکه روزانه")
    return "\n".join(lines)


def render_plans_shop_kb(current_plan: str = "normal") -> dict[str, Any]:
    rows = [[{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}], [{"text": "👥 دعوت دوستان", "callback_data": "plan_referral"}], [{"text": "🪙 فعالیت و کیف پول", "callback_data": "plan_wallet"}]]
    current_idx = PLAN_ORDER.index(current_plan if current_plan in PLAN_ORDER else "normal")
    for key in PLAN_ORDER[current_idx + 1:]:
        cfg = PLANS_DATA[key]
        rows.append([{"text": f"{cfg['badge']} ارتقا به {cfg['title']}", "callback_data": f"plan_buy_{key}"}])
    rows += [[{"text": "📊 داشبورد رنک", "callback_data": "menu_plans"}], [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}]]
    return {"inline_keyboard": rows}


async def handle_plan_callback(bot, cq: dict[str, Any], *, user_id: int, chat_id: int, msg_id: int, data: str) -> bool:
    if data not in {"menu_plans", "plan_catalog", "plan_claim_daily", "plan_referral", "plan_wallet", "menu_account", "menu_invite", "menu_daily"} and not data.startswith("plan_buy_"):
        return False
    profile = await get_user_profile(user_id)
    if not profile:
        await bot.answer_callback(cq["id"], "❌ ابتدا سلف خود را ثبت کنید.", alert=True)
        return True
    if data == "menu_account":
        await bot.answer_callback(cq["id"])
        await bot.edit_message(chat_id, msg_id, render_plan_dashboard(profile), reply_markup={"inline_keyboard": [
            [{"text": "👑 رنک‌ها و ارتقا", "callback_data": "menu_plans"}],
            [{"text": "👥 دعوت از دوستان", "callback_data": "menu_invite"}],
            [{"text": "🎁 سکه و جایزه روزانه", "callback_data": "menu_daily"}],
            [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}],
        ]})
        return True
    if data == "menu_invite":
        data = "plan_referral"
    elif data == "menu_daily":
        data = "plan_claim_daily"

    if data == "menu_plans":
        await bot.answer_callback(cq["id"])
        await bot.edit_message(chat_id, msg_id, render_plan_dashboard(profile), reply_markup={"inline_keyboard": [
            [{"text": "🛍 فروشگاه رنک‌ها", "callback_data": "plan_catalog"}],
            [{"text": "👥 دعوت دوستان", "callback_data": "plan_referral"}],
            [{"text": "🪙 کیف پول و فعالیت", "callback_data": "plan_wallet"}],
            [{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}],
            [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}],
        ]})
        return True
    if data == "plan_catalog":
        await bot.answer_callback(cq["id"])
        await bot.edit_message(chat_id, msg_id, render_plans_catalog(profile), reply_markup=render_plans_shop_kb(profile["plan"]))
        return True
    if data == "plan_claim_daily":
        ok, message = await claim_daily_bonus(user_id)
        await bot.answer_callback(cq["id"], message, alert=True)
        fresh = await get_user_profile(user_id)
        if fresh:
            await bot.edit_message(chat_id, msg_id, render_plan_dashboard(fresh), reply_markup={"inline_keyboard": [
                [{"text": "🛍 فروشگاه رنک‌ها", "callback_data": "plan_catalog"}],
                [{"text": "👥 دعوت دوستان", "callback_data": "plan_referral"}],
                [{"text": "🪙 کیف پول و فعالیت", "callback_data": "plan_wallet"}],
                [{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}],
                [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}],
            ]})
        return True
    if data == "plan_referral":
        me = (await bot.get_me()) if hasattr(bot, "get_me") else None
        username = (me or {}).get("username", "")
        link = f"https://t.me/{username}?start=ref_{user_id}" if username else f"/start ref_{user_id}"
        await bot.answer_callback(cq["id"])
        idx = PLAN_ORDER.index(normalize_plan(profile["plan"]))
        if idx < len(PLAN_ORDER) - 1:
            next_cfg = PLANS_DATA[PLAN_ORDER[idx + 1]]
            remaining = max(0, next_cfg["required_referrals"] - profile["referral_count"])
            progress = f"\n📈 برای {next_cfg['badge']} {next_cfg['title']}: `{remaining}` دعوت دیگر لازم است."
        else:
            progress = "\n👑 شما به بالاترین رنک رسیده‌اید."
        await bot.edit_message(chat_id, msg_id, f"👥 **دعوت دوستان**\n━━━━━━━━━━━━━━━━━━━━\n\n🔗 لینک اختصاصی شما:\n`{link}`\n\n🎁 هر دعوت موفق: `{50}` سکه + `25 XP`\n📊 دعوت‌های موفق: `{profile['referral_count']}`{progress}", reply_markup={"inline_keyboard": [[{"text": "🪙 کیف پول و فعالیت", "callback_data": "plan_wallet"}], [{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}], [{"text": "🔙 بازگشت", "callback_data": "menu_plans"}]]})
        return True
    if data == "plan_wallet":
        cfg = get_plan_config(profile["plan"])
        await bot.answer_callback(cq["id"])
        await bot.edit_message(chat_id, msg_id, f"🪙 **کیف پول و فعالیت**\n\nموجودی: `{profile['coins']}` سکه\nXP: `{profile['activity_score']}`\nپاداش فعالیت هر ۱۰ دقیقه: `+{cfg['activity_coins']} سکه`\nسقف پاداش فعالیت روزانه: `{cfg['activity_daily_cap']} سکه`\nپاداش روزانه: `{cfg['daily_coins']} سکه`\n\nهرچه رنک بالاتر باشد، درآمد فعالیت هم بیشتر می‌شود.", reply_markup={"inline_keyboard": [[{"text": "📈 نمایش رنک‌ها", "callback_data": "plan_catalog"}], [{"text": "🔙 بازگشت", "callback_data": "menu_plans"}]]})
        return True
    target = data.removeprefix("plan_buy_")
    ok, message = await upgrade_user_plan(user_id, target)
    await bot.answer_callback(cq["id"], message, alert=True)
    fresh = await get_user_profile(user_id)
    if fresh:
        await bot.edit_message(chat_id, msg_id, render_plan_dashboard(fresh), reply_markup={"inline_keyboard": [
            [{"text": "🛍 فروشگاه رنک‌ها", "callback_data": "plan_catalog"}],
            [{"text": "👥 دعوت دوستان", "callback_data": "plan_referral"}],
            [{"text": "🪙 کیف پول و فعالیت", "callback_data": "plan_wallet"}],
            [{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}],
            [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}],
        ]})
    return True
