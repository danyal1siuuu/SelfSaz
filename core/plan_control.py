# -*- coding: utf-8 -*-
"""Persistent free/plan validity control system for SelfSaz."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from config import DB_NAME, ADMIN_ID

PLAN_KEYS = ("normal", "iron", "bronze", "silver", "gold", "diamond")
PLAN_LABELS = {
    "normal": "عادی/رایگان",
    "iron": "آهنی",
    "bronze": "برنزی",
    "silver": "نقره‌ای",
    "gold": "طلایی",
    "diamond": "الماسی",
}
DEFAULT_CONFIG: dict[str, Any] = {
    "global_enabled": True,
    "default_days": 15,
    "default_grace_days": 0,
    "default_mode": "rank_referral_only",
    "auto_stop": True,
    "auto_notify": True,
    "scan_interval": 60,
    "notify_before_days": [3, 1],
    "admin_exempt": True,
    "allow_start_expired": True,
    "allow_status_expired": False,
    "allow_recovery_expired": False,
    "notify_on_stop": True,
    "notify_on_unlock": True,
    "stamp_rule_version": True,
    "rules_version": 1,
    "plans": {
        "normal": {"enabled": True, "days": 15, "grace_days": 0, "mode": "rank_referral_only", "allow_referral": True, "allow_rank": True, "start_policy": "registration"},
        "iron": {"enabled": False, "days": 0, "grace_days": 0, "mode": "rank_referral_only", "allow_referral": True, "allow_rank": True, "start_policy": "assignment"},
        "bronze": {"enabled": False, "days": 0, "grace_days": 0, "mode": "rank_referral_only", "allow_referral": True, "allow_rank": True, "start_policy": "assignment"},
        "silver": {"enabled": False, "days": 0, "grace_days": 0, "mode": "rank_referral_only", "allow_referral": True, "allow_rank": True, "start_policy": "assignment"},
        "gold": {"enabled": False, "days": 0, "grace_days": 0, "mode": "rank_referral_only", "allow_referral": True, "allow_rank": True, "start_policy": "assignment"},
        "diamond": {"enabled": False, "days": 0, "grace_days": 0, "mode": "rank_referral_only", "allow_referral": True, "allow_rank": True, "start_policy": "assignment"},
    },
}


def _deep_merge(base: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


async def get_plan_control() -> dict[str, Any]:
    async with aiosqlite.connect(DB_NAME) as db:
        row = await (await db.execute("SELECT value FROM system_settings WHERE key='plan_validity_config'")).fetchone()
    if not row or not row[0]:
        cfg = _deep_merge(DEFAULT_CONFIG, {})
        await save_plan_control(cfg)
        return cfg
    try:
        raw = json.loads(row[0])
        return _deep_merge(DEFAULT_CONFIG, raw if isinstance(raw, dict) else {})
    except Exception:
        return _deep_merge(DEFAULT_CONFIG, {})


async def save_plan_control(cfg: dict[str, Any]) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO system_settings(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            ("plan_validity_config", json.dumps(cfg, ensure_ascii=False), int(time.time())),
        )
        await db.commit()


async def set_plan_control_value(path: str, value: Any) -> dict[str, Any]:
    cfg = await get_plan_control()
    target: dict[str, Any] = cfg
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
    await save_plan_control(cfg)
    return cfg


async def get_plan_rule(plan_key: str) -> dict[str, Any]:
    cfg = await get_plan_control()
    return dict(cfg["plans"].get(plan_key, cfg["plans"]["normal"]))


async def apply_plan_expiry(user_id: int, plan_key: str, *, reset_start: bool = True, force_days: int | None = None) -> tuple[int, int]:
    """Recalculate plan_start/plan_expiry for a user. Returns (started_at, expires_at)."""
    cfg = await get_plan_control()
    rule = cfg["plans"].get(plan_key, cfg["plans"]["normal"])
    now = int(time.time())
    days = int(rule.get("days", cfg.get("default_days", 15)) if force_days is None else force_days)
    enabled = bool(cfg.get("global_enabled", True) and rule.get("enabled", False) and days > 0)
    async with aiosqlite.connect(DB_NAME) as db:
        row = await (await db.execute("SELECT plan_started_at, plan_expires_at FROM users WHERE user_id=?", (user_id,))).fetchone()
        started = now if reset_start or not row or not int(row[0] or 0) else int(row[0])
        expires = started + days * 86400 if enabled else 0
        await db.execute(
            "UPDATE users SET plan_started_at=?, plan_expires_at=?, plan_expired_notified=0, plan_locked=0 WHERE user_id=?",
            (started, expires, user_id),
        )
        await db.commit()
    return started, expires


async def user_plan_state(user_id: int) -> dict[str, Any]:
    async with aiosqlite.connect(DB_NAME) as db:
        row = await (await db.execute(
            "SELECT plan,plan_started_at,plan_expires_at,plan_exempt,plan_locked,plan_expired_notified FROM users WHERE user_id=?",
            (user_id,),
        )).fetchone()
    if not row:
        return {"exists": False, "expired": False, "remaining": None, "plan": "normal"}
    plan = row[0] or "normal"
    cfg = await get_plan_control()
    admin_exempt = bool(cfg.get("admin_exempt", True)) and user_id == int(ADMIN_ID)
    exempt = bool(row[3] or 0) or admin_exempt
    started = int(row[1] or 0)
    expires = int(row[2] or 0)
    locked = bool(row[4] or 0)
    if expires == 0 and started == 0:
        started, expires = await apply_plan_expiry(user_id, plan, reset_start=True)
    if expires == 0 and not exempt:
        cfg = await get_plan_control()
        rule = cfg["plans"].get(plan, cfg["plans"]["normal"])
        days = int(rule.get("days", cfg.get("default_days", 15)) or 0)
        if cfg.get("global_enabled", True) and rule.get("enabled", False) and days > 0:
            started = started or int(time.time())
            expires = started + days * 86400
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("UPDATE users SET plan_started_at=?, plan_expires_at=? WHERE user_id=?", (started, expires, user_id))
                await db.commit()
    rule = cfg["plans"].get(plan, cfg["plans"]["normal"])
    grace_days = int(rule.get("grace_days", cfg.get("default_grace_days", 0)) or 0)
    lock_at = expires + max(0, grace_days) * 86400 if expires else 0
    now = int(time.time())
    expired = bool(not exempt and expires > 0 and now >= lock_at)
    if expired and not locked:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET plan_locked=1 WHERE user_id=?", (user_id,))
            await db.commit()
        locked = True
    return {
        "exists": True,
        "plan": plan,
        "started_at": started,
        "expires_at": expires,
        "remaining": max(0, lock_at - now) if lock_at else None,
        "expired": expired,
        "exempt": exempt,
        "locked": locked,
        "expired_notified": bool(row[5] or 0),
    }


_ALLOWED_EXPIRED_EXACT = {
    "menu_plans", "menu_invite", "plan_catalog", "plan_referral",
    "back_dashboard", "check_membership", "plan_validity_status", "plan_validity_refresh",
}


def expired_callback_allowed(data: str) -> bool:
    return data in _ALLOWED_EXPIRED_EXACT or data.startswith("plan_buy_")



async def can_use_feature(user_id: int, *, is_admin: bool = False) -> tuple[bool, str]:
    if is_admin:
        return True, "admin"
    state = await user_plan_state(user_id)
    if not state.get("exists"):
        return False, "❌ حساب شما ثبت نشده است."
    if not state.get("expired"):
        return True, "active"
    return False, "🔒 اعتبار پلن شما تمام شده است. برای ادامه فقط «رنک‌ها و ارتقا» و «دعوت از دوستان» فعال هستند."


async def enforce_expired_clients(active_clients: dict[int, Any]) -> int:
    now = int(time.time())
    expired_ids: list[int] = []
    async with aiosqlite.connect(DB_NAME) as db:
        rows = await (await db.execute(
            "SELECT user_id,plan,plan_expires_at,plan_exempt,plan_locked FROM users WHERE plan_expires_at>0"
        )).fetchall()
        cfg = await get_plan_control()
        for uid, plan, exp, exempt, locked in rows:
            rule = cfg["plans"].get(plan, cfg["plans"]["normal"])
            grace_days = int(rule.get("grace_days", cfg.get("default_grace_days", 0)) or 0)
            lock_at = int(exp or 0) + max(0, grace_days) * 86400
            if not exempt and lock_at > 0 and lock_at <= now and not locked:
                expired_ids.append(int(uid))
                await db.execute("UPDATE users SET plan_locked=1 WHERE user_id=?", (uid,))
        await db.commit()
    stopped = 0
    for uid in expired_ids:
        cli = active_clients.get(uid)
        if cli is not None:
            try:
                from core.manager import stop_single_client
                await stop_single_client(uid)
                stopped += 1
            except Exception:
                pass
    return stopped


def format_expiry(ts: int | None) -> str:
    if not ts:
        return "بدون انقضا"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def build_admin_action_catalog() -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    def add(label: str, kind: str, **kwargs: Any) -> None:
        actions.append({"label": label, "kind": kind, **kwargs})

    global_specs = [
        ("فعال/خاموش اعتبار پلن‌ها", "global_toggle", "global_enabled"),
        ("تنظیم روز پیش‌فرض پلن رایگان", "global_int", "default_days"),
        ("تنظیم روز مهلت پس از انقضا", "global_int", "default_grace_days"),
        ("تغییر سیاست بعد از انقضا", "cycle_mode", "default_mode"),
        ("توقف خودکار سلف منقضی‌شده", "global_toggle", "auto_stop"),
        ("اعلان قبل از انقضا", "global_toggle", "auto_notify"),
        ("فاصله اسکن اعتبار", "global_int", "scan_interval"),
        ("روزهای اعلان باقی‌مانده", "notify_days_input", "notify_before_days"),
        ("فعال‌سازی اعتبار عادی برای تازه‌وارد", "plan_toggle", ("normal", "enabled")),
        ("شروع مجدد تایمر کاربران قدیمی", "bulk_reset_trial", None),
    ]
    for label, kind, arg in global_specs:
        add("🌐 " + label, kind, arg=arg)

    for pk in PLAN_KEYS:
        for label, field, kind in [
            ("اعتبارسنجی فعال", "enabled", "plan_toggle"),
            ("مدت اعتبار (روز)", "days", "plan_int"),
            ("مهلت پس از انقضا (روز)", "grace_days", "plan_int"),
            ("اجازه دعوت پس از انقضا", "allow_referral", "plan_toggle"),
            ("اجازه ارتقا پس از انقضا", "allow_rank", "plan_toggle"),
        ]:
            add(f"{PLAN_LABELS[pk]} · {label}", kind, arg=(pk, field))

    user_actions = [
        ("بررسی اعتبار کاربر", "user_report"), ("تنظیم مدت کاربر", "user_set_days"),
        ("تمدید اعتبار کاربر", "user_extend_days"), ("انقضای فوری کاربر", "user_expire_now"),
        ("بازکردن اعتبار کاربر", "user_unexpire"), ("استثنای دائمی کاربر", "user_exempt_toggle"),
        ("ریست تایمر کاربر", "user_reset_timer"), ("تنظیم تاریخ انقضای دقیق", "user_set_expiry"),
        ("قفل دستی حساب", "user_lock_toggle"), ("اعمال قواعد پلن فعلی", "user_reapply_plan"),
    ]
    for label, kind in user_actions:
        add("👤 " + label, kind)

    bulk_actions = [
        ("اعمال قوانین روی همه کاربران", "bulk_apply_rules"), ("قفل همه منقضی‌ها", "bulk_lock_expired"),
        ("بازکردن همه کاربران منقضی", "bulk_unlock_all"), ("ریست تایمر تمام عادی‌ها", "bulk_reset_normal"),
        ("تمدید ۱ روز همه منقضی‌ها", "bulk_extend_1"), ("تمدید ۷ روز همه منقضی‌ها", "bulk_extend_7"),
        ("تمدید ۳۰ روز همه منقضی‌ها", "bulk_extend_30"), ("فعال‌سازی استثنا برای الماسی‌ها", "bulk_diamond_exempt"),
        ("غیرفعال‌کردن اعتبار روی الماسی‌ها", "bulk_diamond_unexpire"), ("بازنشانی اعلان‌های انقضا", "bulk_reset_notifications"),
    ]
    for label, kind in bulk_actions: add("🧰 " + label, kind)

    message_actions = [
        ("پیام همگانی کاربران منقضی", "broadcast_expired"), ("پیام همگانی ۳ روز مانده", "broadcast_3d"),
        ("پیام همگانی ۱ روز مانده", "broadcast_1d"), ("پیام یک‌به‌یک براساس آیدی", "dm_user"),
        ("متن یادآوری انقضا", "set_expiry_notice"), ("متن انقضای کامل", "set_expired_notice"),
        ("متن تمدید موفق", "set_extension_notice"), ("متن ارتقای موفق", "set_upgrade_notice"),
        ("متن قفل کامل", "set_lock_notice"), ("پیش‌نمایش پیام انقضا", "preview_expiry_notice"),
    ]
    for label, kind in message_actions: add("📣 " + label, kind)

    report_actions = [
        ("تعداد پلن عادی فعال", "report_normal"), ("تعداد کاربران منقضی", "report_expired"),
        ("تعداد ۳ روز مانده", "report_3d"), ("تعداد ۷ روز مانده", "report_7d"),
        ("تعداد بدون انقضا", "report_unlimited"), ("توزیع اعتبار پلن‌ها", "report_distribution"),
        ("میانگین روزهای باقی‌مانده", "report_avg_remaining"), ("۱۰ انقضای نزدیک", "report_upcoming"),
        ("۱۰ کاربر منقضی اخیر", "report_recent_expired"), ("گزارش کامل اعتبار", "report_full"),
    ]
    for label, kind in report_actions: add("📊 " + label, kind)

    audit_actions = [
        ("ثبت Audit تغییرات اعتبار", "toggle_audit"), ("گزارش Audit اعتبار", "audit_report"),
        ("خروجی Audit اعتبار", "audit_export"), ("آخرین تغییرات پلن", "last_plan_changes"),
        ("آخرین تمدیدها", "last_extensions"), ("آخرین انقضاها", "last_expiries"),
        ("آخرین قفل‌های دستی", "last_locks"), ("آخرین استثناها", "last_exempts"),
        ("پاکسازی Audit قدیمی", "audit_cleanup"), ("تعداد Audit اعتبار", "audit_count"),
    ]
    for label, kind in audit_actions: add("🧾 " + label, kind)

    safety_actions = [
        ("تست موتور اعتبار", "self_test"), ("همگام‌سازی قفل‌ها", "sync_locks"),
        ("بررسی کاربران بدون تایمر", "repair_missing_timers"), ("بررسی انقضاهای نامعتبر", "repair_invalid_expiry"),
        ("تطبیق plan_locked", "repair_locked_flags"), ("پاکسازی اعلان‌های تکراری", "clear_notice_flags"),
        ("بازنشانی کل پیکربندی", "reset_config"), ("ذخیره Snapshot تنظیمات", "snapshot_config"),
        ("بازیابی Snapshot آخر", "restore_snapshot"), ("نمایش JSON تنظیمات", "show_config"),
    ]
    for label, kind in safety_actions: add("🛡 " + label, kind)

    # 10 global + 30 plan + 10 user + 10 bulk + 10 message + 10 report + 10 audit + 10 safety = 100;
    # add 30 explicit per-plan action buttons (5 per plan) for start-policy/mode/report/reset.
    for pk in PLAN_KEYS:
        for label, field, kind in [
            ("سیاست شروع تایمر", "start_policy", "plan_mode"),
            ("سیاست بعد از انقضا", "mode", "plan_mode"),
            ("تعداد کاربران منقضی", None, "plan_report"),
            ("اعمال فوری قانون پلن", None, "plan_apply_all"),
            ("ریست تایمر کاربران پلن", None, "plan_reset_all"),
        ]:
            add(f"{PLAN_LABELS[pk]} · {label}", kind, arg=(pk, field))
    assert len(actions) == 130, len(actions)
    return actions
