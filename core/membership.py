# -*- coding: utf-8 -*-
"""Forced-membership gate for the SelfSaz bot."""
from __future__ import annotations

from typing import Any

import aiohttp
import aiosqlite

from config import BOT_TOKEN, ADMIN_ID
from core.system_settings import get_setting
from database.db import DB_NAME


def _chat_candidates(raw: str) -> list[str]:
    raw = (raw or '').strip()
    if not raw:
        return []
    items = [raw]
    if raw.startswith('https://t.me/'):
        tail = raw.rstrip('/').split('/')[-1]
        if tail:
            items.append('@' + tail.lstrip('@'))
    elif not raw.startswith('@') and '/' not in raw:
        items.append('@' + raw)
    return list(dict.fromkeys(items))


async def forced_join_enabled() -> bool:
    return (await get_setting('force_join_enabled', '0')) == '1'


async def forced_join_target() -> str:
    return await get_setting('force_join_chat', '')


async def forced_join_url() -> str:
    raw = await get_setting('force_join_url', '')
    return raw or await forced_join_target()


async def is_exempt(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute('SELECT 1 FROM membership_exemptions WHERE user_id = ?', (user_id,))
        return bool(await cur.fetchone())


async def _get_chat_member(chat: str, user_id: int) -> dict[str, Any] | None:
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/getChatMember'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={'chat_id': chat, 'user_id': user_id}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                payload = await resp.json()
                return payload.get('result') if payload.get('ok') else None
    except Exception:
        return None


async def check_membership(user_id: int) -> tuple[bool, str]:
    if not await forced_join_enabled() or await is_exempt(user_id):
        return True, ''
    target = await forced_join_target()
    candidates = _chat_candidates(target)
    if not candidates:
        return True, ''
    member = None
    for chat in candidates:
        member = await _get_chat_member(chat, user_id)
        if member is not None:
            break
    if member is None:
        return False, '⚠️ بررسی عضویت کانال اجباری ممکن نشد؛ تنظیم کانال را توسط ادمین بررسی کنید.'
    status = str(member.get('status', ''))
    joined = status in {'creator', 'administrator', 'member'}
    if joined:
        return True, ''
    # Telegram may return restricted users; they count as joined only when not left/kicked.
    if status == 'restricted' and not member.get('is_member'):
        joined = False
    if joined:
        return True, ''
    url = await forced_join_url()
    custom = await get_setting('force_join_text', '🔒 **عضویت اجباری فعال است.**\n\nبرای استفاده از سلف‌ساز ابتدا در کانال/گروه مشخص‌شده عضو شوید؛ سپس روی «✅ بررسی عضویت» بزنید.')
    return False, custom
