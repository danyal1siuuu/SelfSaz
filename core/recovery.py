# -*- coding: utf-8 -*-
"""User-scoped JSON backup/export/import engine."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from config import DB_NAME

BACKUP_VERSION = 2
USER_COLUMNS = [
    "user_id", "session_string", "prefix", "prefix_enabled", "coins", "is_vip", "settings", "plan",
    "activity_score", "last_daily_claim", "previous_plan", "referred_by", "referral_count",
    "last_activity_reward", "activity_reward_date", "activity_reward_coins", "plan_started_at",
    "plan_expires_at", "plan_exempt", "plan_locked", "plan_expired_notified",
]


def _decode_settings(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        obj = json.loads(value) if isinstance(value, str) else value
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


async def export_user_backup(user_id: int, scope: str = "full") -> dict[str, Any]:
    async with aiosqlite.connect(DB_NAME) as db:
        user_row = await (await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))).fetchone()
        if not user_row:
            raise ValueError("کاربر ثبت نشده است.")
        cols = [d[0] for d in await (await db.execute("SELECT * FROM users LIMIT 0")).description]
        user = dict(zip(cols, user_row))
        user["settings"] = _decode_settings(user.get("settings"))
        payload: dict[str, Any] = {
            "format": "SelfSaz User Backup",
            "version": BACKUP_VERSION,
            "scope": scope,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
        }
        if scope in {"full", "session", "settings", "plan", "notifications", "stats", "automations"}:
            if scope == "session":
                payload["user"] = {"user_id": user_id, "session_string": user.get("session_string")}
            elif scope == "settings":
                payload["user"] = {"user_id": user_id, "prefix": user.get("prefix"), "prefix_enabled": user.get("prefix_enabled"), "settings": user.get("settings", {})}
            elif scope == "plan":
                payload["user"] = {k: user.get(k) for k in ("user_id", "coins", "is_vip", "plan", "activity_score", "last_daily_claim", "previous_plan", "referred_by", "referral_count", "last_activity_reward", "activity_reward_date", "activity_reward_coins", "plan_started_at", "plan_expires_at", "plan_exempt", "plan_locked", "plan_expired_notified")}
            elif scope == "stats":
                pass
            elif scope == "notifications":
                pass
            else:
                payload["user"] = user
        if scope in {"full", "relations"}:
            payload["relations"] = [dict(zip(("owner_id", "target_id", "type"), row)) for row in await (await db.execute("SELECT owner_id,target_id,type FROM relations WHERE owner_id=?", (user_id,))).fetchall()]
        if scope in {"full", "notes"}:
            payload["notes"] = [dict(zip(("id", "owner_id", "note", "created_at"), row)) for row in await (await db.execute("SELECT id,owner_id,note,created_at FROM user_notes WHERE owner_id=? ORDER BY id", (user_id,))).fetchall()]
        if scope in {"full", "automations"}:
            st = user.get("settings", {})
            payload["automations"] = {k: v for k, v in st.items() if k.startswith("automation_") or k in {"auto_reply_active", "auto_reply_text", "away_active", "auto_read_active", "monshi_active", "cleaner_active", "cleaner_delay", "timename_active", "timename_font", "fixed_bio_enabled", "fixed_bio_text"}}
        if scope in {"full", "stats"}:
            row = await (await db.execute("SELECT incoming,outgoing,ai_replies,auto_replies,last_incoming_at,last_outgoing_at FROM message_stats WHERE user_id=?", (user_id,))).fetchone()
            payload["message_stats"] = dict(zip(("user_id", "incoming", "outgoing", "ai_replies", "auto_replies", "last_incoming_at", "last_outgoing_at"), (user_id, *(row or (0,0,0,0,0,0)))))
        if scope in {"full", "notifications"}:
            row = await (await db.execute("SELECT user_id,enabled,language,updated_at FROM notification_preferences WHERE user_id=?", (user_id,))).fetchone()
            payload["notification_preferences"] = dict(zip(("user_id", "enabled", "language", "updated_at"), (row or (user_id,1,"fa",int(time.time())))))
        if scope in {"full", "ai", "relations"}:
            rows = await (await db.execute("SELECT trigger,response FROM auto_replies WHERE owner_id=? ORDER BY trigger", (user_id,))).fetchall()
            payload["auto_replies"] = [{"owner_id": user_id, "trigger": trigger, "response": response} for trigger, response in rows]
        if scope in {"full", "plan"}:
            row = await (await db.execute("SELECT user_id,created_at FROM membership_exemptions WHERE user_id=?", (user_id,))).fetchone()
            payload["membership_exemption"] = ({"user_id": int(row[0]), "created_at": int(row[1] or 0)} if row else None)
        if scope in {"full", "ai"}:
            rows = await (await db.execute("SELECT id,user_id,role,content,created_at FROM ai_messages WHERE user_id=? ORDER BY id", (user_id,))).fetchall()
            payload["ai_messages"] = [dict(zip(("id","user_id","role","content","created_at"), row)) for row in rows]
        if scope in {"full", "relations"}:
            rows = await (await db.execute("SELECT referrer_id,referred_id,reward_coins,created_at FROM referrals WHERE referrer_id=? OR referred_id=? ORDER BY created_at", (user_id,user_id))).fetchall()
            payload["referrals"] = [{"referrer_id": int(a), "referred_id": int(b), "reward_coins": int(c or 0), "created_at": int(d or 0)} for a,b,c,d in rows]
        if scope == "full":
            payload["summary"] = {
                "relations": len(payload.get("relations", [])),
                "notes": len(payload.get("notes", [])),
                "ai_messages": len(payload.get("ai_messages", [])),
                "contains_session_string": bool(user.get("session_string")),
            }
        return payload


async def restore_user_backup(user_id: int, payload: dict[str, Any], scope: str = "full") -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("format") != "SelfSaz User Backup":
        raise ValueError("فرمت فایل پشتیبان SelfSaz معتبر نیست.")
    source_uid = int(payload.get("user_id") or 0)
    if source_uid != user_id:
        raise ValueError("این فایل متعلق به همین کاربر نیست.")
    user = payload.get("user") or {}
    async with aiosqlite.connect(DB_NAME) as db:
        existing = await (await db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))).fetchone()
        if not existing:
            await db.execute("INSERT INTO users(user_id) VALUES(?)", (user_id,))
        changed: list[str] = []
        if scope in {"full", "session"} and "session_string" in user:
            await db.execute("UPDATE users SET session_string=? WHERE user_id=?", (user.get("session_string") or None, user_id)); changed.append("session")
        if scope in {"full", "settings"}:
            if "prefix" in user or "prefix_enabled" in user or "settings" in user:
                await db.execute("UPDATE users SET prefix=?,prefix_enabled=?,settings=? WHERE user_id=?", (user.get("prefix", "."), int(bool(user.get("prefix_enabled", 1))), json.dumps(user.get("settings") or {}, ensure_ascii=False), user_id)); changed.append("settings")
        if scope in {"full", "plan"} and any(k in user for k in ("coins","plan","is_vip","plan_started_at","plan_expires_at")):
            keys = [k for k in ("coins","is_vip","plan","activity_score","last_daily_claim","previous_plan","referred_by","referral_count","last_activity_reward","activity_reward_date","activity_reward_coins","plan_started_at","plan_expires_at","plan_exempt","plan_locked","plan_expired_notified") if k in user]
            if keys:
                values = [user[k] for k in keys]
                sql = "UPDATE users SET " + ",".join(f"{k}=?" for k in keys) + " WHERE user_id=?"
                await db.execute(sql, (*values, user_id)); changed.append("plan")
        if scope in {"full", "relations"} and isinstance(payload.get("relations"), list):
            await db.execute("DELETE FROM relations WHERE owner_id=?", (user_id,))
            for item in payload["relations"]:
                if int(item.get("owner_id", user_id)) == user_id:
                    await db.execute("INSERT OR REPLACE INTO relations(owner_id,target_id,type) VALUES(?,?,?)", (user_id, int(item["target_id"]), str(item["type"])))
            if isinstance(payload.get("auto_replies"), list):
                await db.execute("DELETE FROM auto_replies WHERE owner_id=?", (user_id,))
                for item in payload["auto_replies"]:
                    await db.execute("INSERT OR REPLACE INTO auto_replies(owner_id,trigger,response) VALUES(?,?,?)", (user_id, str(item.get("trigger","")), str(item.get("response",""))))
            if isinstance(payload.get("referrals"), list):
                await db.execute("DELETE FROM referrals WHERE referrer_id=? OR referred_id=?", (user_id,user_id))
                for item in payload["referrals"]:
                    a,b=int(item.get("referrer_id",0)),int(item.get("referred_id",0))
                    if user_id in {a,b} and a and b:
                        await db.execute("INSERT OR REPLACE INTO referrals(referrer_id,referred_id,reward_coins,created_at) VALUES(?,?,?,?)", (a,b,int(item.get("reward_coins",0)),int(item.get("created_at") or time.time())))
            changed.append("relations")
        if scope in {"full", "notes"} and isinstance(payload.get("notes"), list):
            await db.execute("DELETE FROM user_notes WHERE owner_id=?", (user_id,))
            for item in payload["notes"]:
                await db.execute("INSERT INTO user_notes(owner_id,note,created_at) VALUES(?,?,?)", (user_id, str(item.get("note", "")), int(item.get("created_at") or time.time())))
            changed.append("notes")
        if scope in {"full", "stats"} and isinstance(payload.get("message_stats"), dict):
            s = payload["message_stats"]
            await db.execute("INSERT INTO message_stats(user_id,incoming,outgoing,ai_replies,auto_replies,last_incoming_at,last_outgoing_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET incoming=excluded.incoming,outgoing=excluded.outgoing,ai_replies=excluded.ai_replies,auto_replies=excluded.auto_replies,last_incoming_at=excluded.last_incoming_at,last_outgoing_at=excluded.last_outgoing_at", (user_id,int(s.get("incoming",0)),int(s.get("outgoing",0)),int(s.get("ai_replies",0)),int(s.get("auto_replies",0)),int(s.get("last_incoming_at",0)),int(s.get("last_outgoing_at",0)))); changed.append("stats")
        if scope in {"full", "notifications"} and isinstance(payload.get("notification_preferences"), dict):
            n = payload["notification_preferences"]
            await db.execute("INSERT INTO notification_preferences(user_id,enabled,language,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled,language=excluded.language,updated_at=excluded.updated_at", (user_id,int(bool(n.get("enabled",1))),str(n.get("language","fa")),int(n.get("updated_at") or time.time()))); changed.append("notifications")
        if scope in {"full", "plan"} and "membership_exemption" in payload:
            await db.execute("DELETE FROM membership_exemptions WHERE user_id=?", (user_id,))
            m = payload.get("membership_exemption")
            if isinstance(m, dict) and int(m.get("user_id", 0)) == user_id:
                await db.execute("INSERT INTO membership_exemptions(user_id,created_at) VALUES(?,?)", (user_id, int(m.get("created_at") or time.time())))
            changed.append("membership")
        if scope in {"full", "ai"} and isinstance(payload.get("ai_messages"), list):
            await db.execute("DELETE FROM ai_messages WHERE user_id=?", (user_id,))
            for item in payload["ai_messages"]:
                await db.execute("INSERT INTO ai_messages(user_id,role,content,created_at) VALUES(?,?,?,?)", (user_id,str(item.get("role","user")),str(item.get("content","")),int(item.get("created_at") or time.time())))
            changed.append("ai")
        await db.commit()
    return {"changed": changed, "user_id": user_id, "session_restored": "session" in changed, "settings_restored": "settings" in changed}
