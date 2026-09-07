# -*- coding: utf-8 -*-
"""OpenAI-compatible AI service with lightweight per-user memory."""
from __future__ import annotations

import time
from typing import Any

import aiohttp
import aiosqlite

from config import AI_API_KEY, AI_BASE_URL, AI_MODEL
from core.system_settings import get_setting
from config import DB_NAME


def _extract_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    choice = choices[0] or {}
    msg = choice.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts).strip()
    text = choice.get("text")
    return text.strip() if isinstance(text, str) else ""


async def ai_available() -> tuple[bool, str]:
    global_enabled = await get_setting("smart_global_enabled", "1") == "1"
    ai_enabled = await get_setting("smart_ai_global", "1") == "1"
    if not global_enabled:
        return False, "قابلیت‌های هوشمند توسط مدیر خاموش شده‌اند."
    if not ai_enabled:
        return False, "هوش مصنوعی سراسری خاموش است."
    if not AI_API_KEY:
        return False, "AI_API_KEY در Railway تنظیم نشده است."
    if not AI_BASE_URL:
        return False, "AI_BASE_URL تنظیم نشده است."
    return True, ""


async def _history(user_id: int, limit: int = 8) -> list[tuple[str, str]]:
    async with aiosqlite.connect(DB_NAME) as db:
        rows = await (await db.execute(
            "SELECT role, content FROM ai_messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )).fetchall()
    return list(reversed(rows))


async def _save_message(user_id: int, role: str, content: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO ai_messages(user_id, role, content, created_at) VALUES(?,?,?,?)",
            (user_id, role, content[:8000], int(time.time())),
        )
        await db.execute(
            "DELETE FROM ai_messages WHERE user_id=? AND id NOT IN (SELECT id FROM ai_messages WHERE user_id=? ORDER BY id DESC LIMIT 20)",
            (user_id, user_id),
        )
        await db.commit()


async def ask_ai(user_id: int, prompt: str, *, system_prompt: str | None = None, remember: bool = True,
                 temperature: float = 0.6, max_tokens: int = 300) -> tuple[str | None, str | None]:
    ok, reason = await ai_available()
    if not ok:
        return None, reason
    system = system_prompt or await get_setting(
        "smart_default_prompt",
        "شما منشی و دستیار هوشمند یک اکانت تلگرام هستید. مودب، طبیعی، کوتاه و کاربردی پاسخ بدهید.",
    )
    model = await get_setting("smart_ai_model", "") or AI_MODEL
    base_url = (await get_setting("smart_ai_base_url", "") or AI_BASE_URL).rstrip("/")
    context = await _history(user_id, 8) if remember else []
    messages = [{"role": "system", "content": system[:6000]}]
    for role, content in context:
        if role in {"user", "assistant"}:
            messages.append({"role": role, "content": content[:4000]})
    messages.append({"role": "user", "content": prompt[:6000]})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
                body = await resp.text()
                if resp.status != 200:
                    return None, f"سرویس AI با وضعیت {resp.status} پاسخ داد: {body[:350]}"
                try:
                    data = __import__("json").loads(body)
                except Exception:
                    return None, "پاسخ سرویس AI JSON معتبر نبود."
        answer = _extract_text(data)
        if not answer:
            return None, "سرویس AI پاسخ متنی برنگرداند."
        if remember:
            await _save_message(user_id, "user", prompt)
            await _save_message(user_id, "assistant", answer)
        return answer, None
    except Exception as exc:
        return None, f"خطای اتصال AI: {type(exc).__name__}"


async def clear_ai_memory(user_id: int | None = None) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        if user_id is None:
            cur = await db.execute("DELETE FROM ai_messages")
        else:
            cur = await db.execute("DELETE FROM ai_messages WHERE user_id=?", (user_id,))
        await db.commit()
        return cur.rowcount


async def ai_stats() -> dict[str, int]:
    async with aiosqlite.connect(DB_NAME) as db:
        users = (await (await db.execute("SELECT COUNT(DISTINCT user_id) FROM ai_messages")).fetchone())[0]
        messages = (await (await db.execute("SELECT COUNT(*) FROM ai_messages")).fetchone())[0]
        replies = (await (await db.execute("SELECT COALESCE(SUM(ai_replies),0) FROM message_stats")).fetchone())[0]
    return {"users": users, "messages": messages, "replies": replies}
