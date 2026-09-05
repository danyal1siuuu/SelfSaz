# -*- coding: utf-8 -*-
import time
import aiosqlite
from config import DB_NAME

PLANS_DATA = {
    "iron": {
        "title": "آهنی (کاربر پایه)",
        "badge": "⛓️",
        "price_coins": 0,
        "max_friends": 5,
        "max_enemies": 5,
        "allowed_fonts": [1, 2],
        "min_cleaner_delay": 20,
        "ai_monshi": False,
        "anti_delete_logger": False,
        "daily_coins": 10,
        "max_yt_mb": 100  # ۱۰۰ مگابایت
    },
    "bronze": {
        "title": "برنزی (کاربر فعال)",
        "badge": "🥉",
        "price_coins": 150,
        "max_friends": 15,
        "max_enemies": 15,
        "allowed_fonts": [1, 2, 3, 4],
        "min_cleaner_delay": 15,
        "ai_monshi": False,
        "anti_delete_logger": True,
        "daily_coins": 25,
        "max_yt_mb": 250  # ۲۵۰ مگابایت
    },
    "silver": {
        "title": "نقره‌ای (نیمه‌حرفه‌ای)",
        "badge": "🥈",
        "price_coins": 350,
        "max_friends": 40,
        "max_enemies": 40,
        "allowed_fonts": [1, 2, 3, 4, 5, 6],
        "min_cleaner_delay": 10,
        "ai_monshi": True,
        "anti_delete_logger": True,
        "daily_coins": 50,
        "max_yt_mb": 500  # ۵۰۰ مگابایت
    },
    "gold": {
        "title": "طلایی (پیشرفته)",
        "badge": "🥇",
        "price_coins": 750,
        "max_friends": 100,
        "max_enemies": 100,
        "allowed_fonts": list(range(1, 11)),
        "min_cleaner_delay": 5,
        "ai_monshi": True,
        "anti_delete_logger": True,
        "daily_coins": 100,
        "max_yt_mb": 1024  # ۱ گیگابایت
    },
    "diamond": {
        "title": "الماسی (نامحدود و VIP)",
        "badge": "💎",
        "price_coins": 1500,
        "max_friends": 9999,
        "max_enemies": 9999,
        "allowed_fonts": list(range(1, 11)),
        "min_cleaner_delay": 1,
        "ai_monshi": True,
        "anti_delete_logger": True,
        "daily_coins": 250,
        "max_yt_mb": 2048  # نامحدود (حداکثر سقف مجاز تلگرام: ۲ گیگابایت)
    }
}

PLAN_ORDER = ["iron", "bronze", "silver", "gold", "diamond"]

def create_progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "▰" * length
    fraction = min(1.0, max(0.0, current / total))
    filled = int(fraction * length)
    return "▰" * filled + "▱" * (length - filled)

async def get_user_profile(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT coins, plan, activity_score, last_daily_claim FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "coins": row[0] or 0,
            "plan": row[1] or "iron",
            "activity_score": row[2] or 0,
            "last_daily": row[3] or 0
        }

async def get_user_yt_limit_mb(user_id: int) -> int:
    """دریافت سقف حجم دانلود یوتیوب به مگابایت برای کاربر"""
    prof = await get_user_profile(user_id)
    plan_key = prof["plan"] if prof else "iron"
    cfg = PLANS_DATA.get(plan_key, PLANS_DATA["iron"])
    return cfg.get("max_yt_mb", 100)

async def add_activity(user_id: int, points: int = 1, bonus_coins: int = 1):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            UPDATE users 
            SET activity_score = COALESCE(activity_score, 0) + ?,
                coins = COALESCE(coins, 0) + ?
            WHERE user_id = ?
            """,
            (points, bonus_coins, user_id)
        )
        await db.commit()

async def claim_daily_bonus(user_id: int):
    now = int(time.time())
    prof = await get_user_profile(user_id)
    if not prof:
        return False, "کاربر یافت نشد."

    if now - prof["last_daily"] < 86400:
        rem_hours = (86400 - (now - prof["last_daily"])) // 3600
        rem_mins = ((86400 - (now - prof["last_daily"])) % 3600) // 60
        return False, f"⏳ پاداش امروز را قبلاً دریافت کرده‌اید!\nزمان باقی‌مانده: `{rem_hours}` ساعت و `{rem_mins}` دقیقه."

    plan_cfg = PLANS_DATA.get(prof["plan"], PLANS_DATA["iron"])
    reward = plan_cfg["daily_coins"]

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ?, last_daily_claim = ? WHERE user_id = ?",
            (reward, now, user_id)
        )
        await db.commit()

    return True, f"🎁 تبریک! مقدار `{reward}` سکه پاداش رتبه {plan_cfg['badge']} به حسابتان اضافه شد."

async def upgrade_user_plan(user_id: int, target_plan: str):
    if target_plan not in PLANS_DATA:
        return False, "پلن نامعتبر است."

    target_cfg = PLANS_DATA[target_plan]
    prof = await get_user_profile(user_id)
    if not prof:
        return False, "کاربر یافت نشد."

    cur_idx = PLAN_ORDER.index(prof["plan"]) if prof["plan"] in PLAN_ORDER else 0
    tgt_idx = PLAN_ORDER.index(target_plan)

    if tgt_idx <= cur_idx:
        return False, "شما در حال حاضر این رتبه یا رتبه‌ای بالاتر از آن را دارید!"

    price = target_cfg["price_coins"]
    if prof["coins"] < price:
        return False, f"❌ سکه کافی ندارید!\nنیاز: `{price}` | موجودی: `{prof['coins']}` سکه"

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET coins = coins - ?, plan = ? WHERE user_id = ?",
            (price, target_plan, user_id)
        )
        await db.commit()

    return True, f"🎉 ارتقا انجام شد!\nرتبه شما به **{target_cfg['badge']} {target_cfg['title']}** ارتقا یافت."

def render_plan_dashboard(prof: dict) -> str:
    plan_key = prof["plan"]
    cfg = PLANS_DATA.get(plan_key, PLANS_DATA["iron"])
    
    cur_idx = PLAN_ORDER.index(plan_key) if plan_key in PLAN_ORDER else 0
    next_plan_str = "👑 حداکثر سطح (الماسی)"
    progress_bar = "▰▰▰▰▰▰▰▰▰▰"
    coins_needed_txt = "تکمیل شده"

    if cur_idx < len(PLAN_ORDER) - 1:
        next_key = PLAN_ORDER[cur_idx + 1]
        next_cfg = PLANS_DATA[next_key]
        next_plan_str = f"{next_cfg['badge']} {next_cfg['title']}"
        progress_bar = create_progress_bar(prof["coins"], next_cfg["price_coins"])
        diff = max(0, next_cfg["price_coins"] - prof["coins"])
        coins_needed_txt = f"`{diff}` سکه تا ارتقا"

    yt_limit_text = f"{cfg['max_yt_mb']} مگابایت" if cfg['max_yt_mb'] < 2048 else "نامحدود (سقف تلگرام ۲ گیگ)"

    return (
        f"👑 **مرکز مدیریت رتبه و پلن اشتراک سلف‌ساز**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **رتبه فعلی:** {cfg['badge']} **{cfg['title']}**\n"
        f"💰 **موجودی حساب:** `{prof['coins']}` سکه\n"
        f"⚡️ **امتیاز فعالیت:** `{prof['activity_score']}` XP\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **پیشرفت به سوی {next_plan_str}:**\n"
        f"[{progress_bar}] ({coins_needed_txt})\n\n"
        f"📋 **امکانات و لیمیت‌های رتبه شما:**\n"
        f"• سقف دانلود یوتیوب: `{yt_limit_text}` 📹\n"
        f"• سقف دوستان / دشمنان: `{cfg['max_friends']}` نفر\n"
        f"• هوش مصنوعی منشی: `{'فعال ✅' if cfg['ai_monshi'] else 'قفل 🔒'}`\n"
        f"• تایمر پاکساز پیام: حداقل `{cfg['min_cleaner_delay']} ثانیه`\n"
        f"• فونت‌های ساعت: `{len(cfg['allowed_fonts'])} از ۱۰`\n"
        f"• پاداش ورود روزانه: `{cfg['daily_coins']}` سکه\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 _با ارسال دستور یا دکمه پاداش روزانه، سکه دریافت کنید._"
    )

def render_plans_shop_kb():
    kb = [
        [{"text": "🎁 دریافت جایزه روزانه (سکه رایگان)", "callback_data": "plan_claim_daily"}],
        [
            {"text": "🥉 ارتقا به برنزی (۱۵۰ سکه)", "callback_data": "plan_buy_bronze"},
            {"text": "🥈 ارتقا به نقره‌ای (۳۵۰ سکه)", "callback_data": "plan_buy_silver"}
        ],
        [
            {"text": "🥇 ارتقا به طلایی (۷۵۰ سکه)", "callback_data": "plan_buy_gold"},
            {"text": "💎 ارتقا به الماسی (۱۵۰۰ سکه)", "callback_data": "plan_buy_diamond"}
        ],
        [{"text": "🔄 بروزرسانی وضعیت", "callback_data": "menu_plans"}],
        [{"text": "🔙 بازگشت به داشبورد اصلی", "callback_data": "back_dashboard"}]
    ]
    return {"inline_keyboard": kb}
