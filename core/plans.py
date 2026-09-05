# -*- coding: utf-8 -*-
"""Centralized subscription/plan engine for SelfSaz.

All plan definitions, feature gates, coin economy and plan UI live here so
host_bot/bot.py only needs a small integration hook.
"""
from __future__ import annotations

import time
from typing import Any

import aiosqlite

from config import DB_NAME

# Order is intentionally linear: users may only upgrade to a higher tier.
PLAN_ORDER = ["normal", "iron", "bronze", "silver", "gold", "diamond"]

# max_yt_mb=None means there is no plan-level size cap.
# The actual Telegram upload limit still applies to whichever Telegram client
# is used to send the resulting file.
PLANS_DATA: dict[str, dict[str, Any]] = {
    "normal": {
        "title": "عادی",
        "short_title": "عادی",
        "badge": "👤",
        "price_coins": 0,
        "max_friends": 3,
        "max_enemies": 3,
        "allowed_fonts": [1, 2],
        "min_cleaner_delay": 60,
        "ai_monshi": False,
        "anti_delete_logger": False,
        "daily_coins": 5,
        "max_yt_mb": 100,
        "description": "شروع رایگان برای استفاده‌های پایه",
    },
    "iron": {
        "title": "آهنی",
        "short_title": "آهنی",
        "badge": "⛓️",
        "price_coins": 100,
        "max_friends": 5,
        "max_enemies": 5,
        "allowed_fonts": [1, 2, 3],
        "min_cleaner_delay": 30,
        "ai_monshi": False,
        "anti_delete_logger": True,
        "daily_coins": 10,
        "max_yt_mb": 250,
        "description": "پایه تقویت‌شده با امکانات بیشتر",
    },
    "bronze": {
        "title": "برنزی",
        "short_title": "برنزی",
        "badge": "🥉",
        "price_coins": 250,
        "max_friends": 15,
        "max_enemies": 15,
        "allowed_fonts": [1, 2, 3, 4, 5],
        "min_cleaner_delay": 20,
        "ai_monshi": False,
        "anti_delete_logger": True,
        "daily_coins": 25,
        "max_yt_mb": 500,
        "description": "برای کاربران فعال با سقف‌های بالاتر",
    },
    "silver": {
        "title": "نقره‌ای",
        "short_title": "نقره‌ای",
        "badge": "🥈",
        "price_coins": 500,
        "max_friends": 40,
        "max_enemies": 40,
        "allowed_fonts": list(range(1, 8)),
        "min_cleaner_delay": 10,
        "ai_monshi": True,
        "anti_delete_logger": True,
        "daily_coins": 50,
        "max_yt_mb": 1024,
        "description": "سطح نیمه‌حرفه‌ای با منشی هوشمند",
    },
    "gold": {
        "title": "طلایی",
        "short_title": "طلایی",
        "badge": "🥇",
        "price_coins": 1000,
        "max_friends": 100,
        "max_enemies": 100,
        "allowed_fonts": list(range(1, 11)),
        "min_cleaner_delay": 5,
        "ai_monshi": True,
        "anti_delete_logger": True,
        "daily_coins": 100,
        "max_yt_mb": 2048,
        "description": "سطح حرفه‌ای برای استفاده سنگین",
    },
    "diamond": {
        "title": "الماسی",
        "short_title": "الماسی",
        "badge": "💎",
        "price_coins": 2000,
        "max_friends": 9999,
        "max_enemies": 9999,
        "allowed_fonts": list(range(1, 11)),
        "min_cleaner_delay": 1,
        "ai_monshi": True,
        "anti_delete_logger": True,
        "daily_coins": 250,
        "max_yt_mb": None,
        "description": "VIP کامل؛ بدون سقف پلن برای حجم یوتیوب",
    },
}


def get_plan_config(plan_key: str | None) -> dict[str, Any]:
    """Return a valid plan config, falling back to the free plan."""
    return PLANS_DATA.get(plan_key or "normal", PLANS_DATA["normal"])


def normalize_plan(plan_key: str | None, is_vip: int | bool = 0) -> str:
    """Normalize legacy/invalid DB values and preserve the old VIP flag."""
    if is_vip:
        return "diamond"
    if plan_key in PLANS_DATA:
        return str(plan_key)
    # Old deployments had no plan column. Treat missing/invalid values as free.
    return "normal"


def format_mb(value: int | None) -> str:
    if value is None:
        return "نامحدود"
    if value >= 1024:
        gb = value / 1024
        return f"{gb:g} گیگابایت"
    return f"{value} مگابایت"


def create_progress_bar(current: int, total: int, length: int = 12) -> str:
    if total <= 0:
        return "▰" * length
    fraction = min(1.0, max(0.0, current / total))
    filled = int(fraction * length)
    return "▰" * filled + "▱" * (length - filled)


async def get_user_profile(user_id: int) -> dict[str, Any] | None:
    """Read one user's complete plan profile."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
            SELECT coins, plan, activity_score, last_daily_claim,
                   is_vip, previous_plan
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()

    if not row:
        return None

    plan = normalize_plan(row[1], row[4])
    return {
        "coins": int(row[0] or 0),
        "plan": plan,
        "activity_score": int(row[2] or 0),
        "last_daily": int(row[3] or 0),
        "is_vip": bool(row[4]),
        "previous_plan": normalize_plan(row[5], 0),
    }


async def get_user_yt_limit_mb(user_id: int) -> int | None:
    profile = await get_user_profile(user_id)
    cfg = get_plan_config(profile["plan"] if profile else "normal")
    return cfg["max_yt_mb"]


async def get_user_plan_name(user_id: int) -> str:
    profile = await get_user_profile(user_id)
    if not profile:
        return "normal"
    return profile["plan"]


async def has_feature(user_id: int, feature: str) -> bool:
    profile = await get_user_profile(user_id)
    cfg = get_plan_config(profile["plan"] if profile else "normal")
    return bool(cfg.get(feature, False))


async def get_relation_limit(user_id: int, relation_type: str) -> int:
    profile = await get_user_profile(user_id)
    cfg = get_plan_config(profile["plan"] if profile else "normal")
    return int(cfg["max_friends"] if relation_type == "friend" else cfg["max_enemies"])


async def get_cleaner_min_delay(user_id: int) -> int:
    profile = await get_user_profile(user_id)
    cfg = get_plan_config(profile["plan"] if profile else "normal")
    return int(cfg["min_cleaner_delay"])


async def get_allowed_fonts(user_id: int) -> list[int]:
    profile = await get_user_profile(user_id)
    cfg = get_plan_config(profile["plan"] if profile else "normal")
    return list(cfg["allowed_fonts"])


async def add_activity(user_id: int, points: int = 1, bonus_coins: int = 0) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            UPDATE users
            SET activity_score = COALESCE(activity_score, 0) + ?,
                coins = COALESCE(coins, 0) + ?
            WHERE user_id = ?
            """,
            (points, bonus_coins, user_id),
        )
        await db.commit()


async def claim_daily_bonus(user_id: int) -> tuple[bool, str]:
    now = int(time.time())
    profile = await get_user_profile(user_id)
    if not profile:
        return False, "❌ کاربر یافت نشد."

    elapsed = now - profile["last_daily"]
    if elapsed < 86400:
        remain = 86400 - elapsed
        hours, rem = divmod(remain, 3600)
        minutes = rem // 60
        return False, f"⏳ پاداش امروز قبلاً دریافت شده است.\nزمان باقی‌مانده: `{hours}` ساعت و `{minutes}` دقیقه."

    cfg = get_plan_config(profile["plan"])
    reward = int(cfg["daily_coins"])

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET coins = COALESCE(coins, 0) + ?, last_daily_claim = ?, activity_score = COALESCE(activity_score, 0) + 5 WHERE user_id = ?",
            (reward, now, user_id),
        )
        await db.commit()

    return True, f"🎁 `{reward}` سکه + `5 XP` دریافت کردی؛ پاداش روزانه {cfg['badge']} {cfg['short_title']} ثبت شد."


async def upgrade_user_plan(user_id: int, target_plan: str) -> tuple[bool, str]:
    if target_plan not in PLANS_DATA:
        return False, "❌ پلن نامعتبر است."

    profile = await get_user_profile(user_id)
    if not profile:
        return False, "❌ کاربر یافت نشد."

    current = normalize_plan(profile["plan"])
    current_idx = PLAN_ORDER.index(current)
    target_idx = PLAN_ORDER.index(target_plan)
    if target_idx <= current_idx:
        return False, "⚠️ این پلن در سطح فعلی شماست یا پایین‌تر از آن قرار دارد."

    target_cfg = PLANS_DATA[target_plan]
    price = int(target_cfg["price_coins"])
    balance = int(profile["coins"])
    if balance < price:
        return False, f"❌ سکه کافی نیست.\nنیاز: `{price}` | موجودی: `{balance}` سکه"

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET coins = coins - ?, plan = ?, is_vip = ? WHERE user_id = ?",
            (price, target_plan, 1 if target_plan == "diamond" else 0, user_id),
        )
        await db.commit()

    return True, f"🎉 پلن شما به **{target_cfg['badge']} {target_cfg['title']}** ارتقا یافت."


async def set_admin_vip(user_id: int, enabled: bool) -> tuple[bool, str]:
    """Compatibility bridge for the existing admin VIP buttons."""
    profile = await get_user_profile(user_id)
    if not profile:
        return False, "❌ کاربر یافت نشد."

    async with aiosqlite.connect(DB_NAME) as db:
        if enabled:
            await db.execute(
                "UPDATE users SET previous_plan = ?, plan = 'diamond', is_vip = 1 WHERE user_id = ?",
                (profile["plan"], user_id),
            )
            msg = "💎 کاربر به پلن الماسی/VIP منتقل شد."
        else:
            restore = profile.get("previous_plan") or "normal"
            if restore == "diamond":
                restore = "normal"
            await db.execute(
                "UPDATE users SET previous_plan = 'normal', plan = ?, is_vip = 0 WHERE user_id = ?",
                (restore, user_id),
            )
            msg = f"🚫 VIP لغو شد و پلن کاربر به `{restore}` بازگردانده شد."
        await db.commit()
    return True, msg


def render_plan_dashboard(profile: dict[str, Any]) -> str:
    plan_key = normalize_plan(profile.get("plan"), profile.get("is_vip", 0))
    cfg = get_plan_config(plan_key)
    idx = PLAN_ORDER.index(plan_key)

    if idx < len(PLAN_ORDER) - 1:
        next_key = PLAN_ORDER[idx + 1]
        next_cfg = PLANS_DATA[next_key]
        diff = max(0, next_cfg["price_coins"] - profile["coins"])
        next_text = f"{next_cfg['badge']} {next_cfg['title']}"
        progress = create_progress_bar(profile["coins"], next_cfg["price_coins"])
        progress_text = f"[{progress}] | `{diff}` سکه تا ارتقا"
    else:
        next_text = "👑 حداکثر سطح"
        progress_text = "[▰▰▰▰▰▰▰▰▰▰▰▰] | تکمیل شده ✅"

    yt = format_mb(cfg["max_yt_mb"])
    fonts = len(cfg["allowed_fonts"])
    return (
        "👑 **مرکز مدیریت پلن سلف‌ساز**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 رتبه فعلی: {cfg['badge']} **{cfg['title']}**\n"
        f"💰 موجودی: `{profile['coins']}` سکه\n"
        f"⚡️ فعالیت: `{profile['activity_score']}` XP\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 مقصد بعدی: **{next_text}**\n{progress_text}\n\n"
        "📋 **سقف‌ها و امکانات فعال**\n"
        f"📹 یوتیوب: `{yt}`\n"
        f"❤️ دوستان: `{cfg['max_friends']}` | ⚔️ دشمنان: `{cfg['max_enemies']}`\n"
        f"⏰ حداقل تایمر پاکسازی: `{cfg['min_cleaner_delay']} ثانیه`\n"
        f"🔤 فونت ساعت: `{fonts}/10`\n"
        f"🤖 منشی هوشمند: `{'فعال ✅' if cfg['ai_monshi'] else 'قفل 🔒'}`\n"
        f"🛡 لاگر حذف/ادیت: `{'فعال ✅' if cfg['anti_delete_logger'] else 'قفل 🔒'}`\n"
        f"🎁 پاداش روزانه: `{cfg['daily_coins']}` سکه\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


def render_plans_catalog(profile: dict[str, Any]) -> str:
    current = normalize_plan(profile.get("plan"), profile.get("is_vip", 0))
    lines = [
        "🛍 **فروشگاه پلن‌های سلف‌ساز**",
        "━━━━━━━━━━━━━━━━━━━━",
        "سقف یوتیوب از **۱۰۰ مگابایت** شروع می‌شود و در الماسی به **نامحدودِ سطح پلن** می‌رسد.",
        "",
    ]
    for key in PLAN_ORDER:
        cfg = PLANS_DATA[key]
        marker = "✅ پلن فعلی" if key == current else f"💰 {cfg['price_coins']} سکه"
        lines.append(
            f"{cfg['badge']} **{cfg['title']}** — {marker}\n"
            f"   📹 {format_mb(cfg['max_yt_mb'])} | 👥 {cfg['max_friends']}/{cfg['max_enemies']} | 🔤 {len(cfg['allowed_fonts'])} فونت | 🤖 {'✅' if cfg['ai_monshi'] else '🔒'}"
        )
    return "\n".join(lines)


def render_plans_shop_kb(current_plan: str = "normal") -> dict[str, Any]:
    rows = [[{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}]]
    purchase_row = []
    for key in PLAN_ORDER[1:]:
        cfg = PLANS_DATA[key]
        if PLAN_ORDER.index(key) > PLAN_ORDER.index(current_plan):
            purchase_row.append({
                "text": f"{cfg['badge']} {cfg['title']} · {cfg['price_coins']}🪙",
                "callback_data": f"plan_buy_{key}",
            })
        if len(purchase_row) == 2:
            rows.append(purchase_row)
            purchase_row = []
    if purchase_row:
        rows.append(purchase_row)
    rows.extend([
        [{"text": "📊 داشبورد پلن", "callback_data": "menu_plans"}],
        [{"text": "🔙 بازگشت به داشبورد", "callback_data": "back_dashboard"}],
    ])
    return {"inline_keyboard": rows}


async def handle_plan_callback(bot, cq: dict[str, Any], *, user_id: int, chat_id: int, msg_id: int, data: str) -> bool:
    """Handle all plan-related callbacks. Returns True when consumed."""
    if data not in {"menu_plans", "plan_catalog", "plan_claim_daily"} and not data.startswith("plan_buy_"):
        return False

    profile = await get_user_profile(user_id)
    if not profile:
        await bot.answer_callback(cq["id"], "❌ ابتدا سلف خود را ثبت کنید.", alert=True)
        return True

    if data == "menu_plans":
        await bot.answer_callback(cq["id"])
        await bot.edit_message(
            chat_id,
            msg_id,
            render_plan_dashboard(profile),
            reply_markup={"inline_keyboard": [
                [{"text": "🛍 مشاهده همه پلن‌ها", "callback_data": "plan_catalog"}],
                [{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}],
                [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}],
            ]},
        )
        return True

    if data == "plan_catalog":
        await bot.answer_callback(cq["id"])
        await bot.edit_message(
            chat_id,
            msg_id,
            render_plans_catalog(profile),
            reply_markup=render_plans_shop_kb(profile["plan"]),
        )
        return True

    if data == "plan_claim_daily":
        ok, message = await claim_daily_bonus(user_id)
        await bot.answer_callback(cq["id"], message, alert=True)
        fresh = await get_user_profile(user_id)
        if fresh:
            await bot.edit_message(
                chat_id,
                msg_id,
                render_plan_dashboard(fresh),
                reply_markup={"inline_keyboard": [
                    [{"text": "🛍 مشاهده همه پلن‌ها", "callback_data": "plan_catalog"}],
                    [{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}],
                    [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}],
                ]},
            )
        return True

    target = data.removeprefix("plan_buy_")
    ok, message = await upgrade_user_plan(user_id, target)
    await bot.answer_callback(cq["id"], message, alert=True)
    fresh = await get_user_profile(user_id)
    if fresh:
        await bot.edit_message(
            chat_id,
            msg_id,
            render_plan_dashboard(fresh),
            reply_markup={"inline_keyboard": [
                [{"text": "🛍 مشاهده همه پلن‌ها", "callback_data": "plan_catalog"}],
                [{"text": "🎁 جایزه روزانه", "callback_data": "plan_claim_daily"}],
                [{"text": "🔙 بازگشت", "callback_data": "back_dashboard"}],
            ]},
        )
    return True
