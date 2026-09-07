# -*- coding: utf-8 -*-
import aiosqlite
from config import DB_NAME


async def _ensure_column(db, table: str, column: str, definition: str):
    cursor = await db.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in await cursor.fetchall()}
    if column not in existing:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                session_string TEXT,
                prefix TEXT DEFAULT '.',
                prefix_enabled INTEGER DEFAULT 1,
                coins INTEGER DEFAULT 100,
                is_vip INTEGER DEFAULT 0,
                settings TEXT DEFAULT '{}',
                plan TEXT DEFAULT 'normal',
                activity_score INTEGER DEFAULT 0,
                last_daily_claim INTEGER DEFAULT 0,
                previous_plan TEXT DEFAULT 'normal'
            )
            """
        )

        # Safe migrations for existing databases.
        await _ensure_column(db, "users", "settings", "TEXT DEFAULT '{}'")
        await _ensure_column(db, "users", "prefix", "TEXT DEFAULT '.'")
        await _ensure_column(db, "users", "prefix_enabled", "INTEGER DEFAULT 1")
        await _ensure_column(db, "users", "coins", "INTEGER DEFAULT 100")
        await _ensure_column(db, "users", "is_vip", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "plan", "TEXT DEFAULT 'normal'")
        await _ensure_column(db, "users", "activity_score", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "last_daily_claim", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "previous_plan", "TEXT DEFAULT 'normal'")
        await _ensure_column(db, "users", "referred_by", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "referral_count", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "last_activity_reward", "INTEGER DEFAULT 0")
        await _ensure_column(db, "users", "activity_reward_date", "TEXT DEFAULT ''")
        await _ensure_column(db, "users", "activity_reward_coins", "INTEGER DEFAULT 0")

        # Normalize legacy rows. Existing VIP users become diamond; everyone
        # else gets the free normal plan unless they already have a valid plan.
        await db.execute("UPDATE users SET plan = 'diamond' WHERE COALESCE(is_vip, 0) = 1")
        await db.execute(
            "UPDATE users SET plan = 'normal' WHERE plan IS NULL OR plan NOT IN ('normal','iron','bronze','silver','gold','diamond')"
        )
        await db.execute("UPDATE users SET previous_plan = 'normal' WHERE previous_plan IS NULL OR previous_plan = ''")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER PRIMARY KEY,
                reward_coins INTEGER DEFAULT 50,
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at INTEGER DEFAULT (strftime('%s','now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER NOT NULL,
                target_id INTEGER,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '',
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS membership_exemptions (
                user_id INTEGER PRIMARY KEY,
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_preferences (
                user_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                language TEXT DEFAULT 'fa',
                updated_at INTEGER DEFAULT (strftime('%s','now'))
            )
            """
        )

        # Defaults for optional global controls.
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('force_join_enabled', '0')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('force_join_chat', '')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('force_join_url', '')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('force_join_text', '🔒 برای استفاده از سلف‌ساز، ابتدا عضو کانال حامی شوید.')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('global_prefix', '.')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('global_download_limit_mb', '2048')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('welcome_text', '')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('bot_status_text', '')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('smart_ai_cooldown', '10')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('smart_default_autoreply', 'سلام! پیام شما دریافت شد؛ به محض فرصت پاسخ می‌دهم. 🙏')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('smart_default_prompt', 'شما منشی و دستیار هوشمند یک اکانت تلگرام هستید. مودب، طبیعی، کوتاه و کاربردی پاسخ بدهید. خود را انسان جا نزنید و اطلاعات محرمانه را درخواست نکنید.')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('smart_ai_global', '1')")
        await db.execute("INSERT OR IGNORE INTO system_settings(key, value) VALUES ('smart_global_enabled', '1')")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS relations (
                owner_id INTEGER,
                target_id INTEGER,
                type TEXT,
                PRIMARY KEY (owner_id, target_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_replies (
                owner_id INTEGER,
                trigger TEXT,
                response TEXT,
                PRIMARY KEY (owner_id, trigger)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                note TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS message_stats (
                user_id INTEGER PRIMARY KEY,
                incoming INTEGER DEFAULT 0,
                outgoing INTEGER DEFAULT 0,
                ai_replies INTEGER DEFAULT 0,
                auto_replies INTEGER DEFAULT 0,
                last_incoming_at INTEGER DEFAULT 0,
                last_outgoing_at INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
            """
        )
        await db.commit()
