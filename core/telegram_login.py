# -*- coding: utf-8 -*-
"""Secure Telegram user authorization using Telegram's official QR-login flow."""
from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid

import qrcode
from pyrogram import Client as PyroClient
from pyrogram.handlers import RawUpdateHandler
from pyrogram.raw.functions import auth
from pyrogram.raw.types import UpdateLoginToken
from pyrogram.raw.types import auth as auth_types


def _qr_path(user_id: int) -> str:
    os.makedirs("downloads", exist_ok=True)
    return os.path.join("downloads", f"qr_login_{user_id}_{uuid.uuid4().hex[:8]}.png")


async def _export(client: PyroClient):
    return await client.invoke(
        auth.ExportLoginToken(
            api_id=client.api_id,
            api_hash=client.api_hash,
            except_ids=[],
        )
    )


async def create_qr_login(api_id: int, api_hash: str, user_id: int) -> dict:
    client = PyroClient(
        name=f":qr:{user_id}:{uuid.uuid4().hex}",
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True,
    )
    await client.connect()

    token = await _export(client)
    if not isinstance(token, auth_types.LoginToken):
        await client.disconnect()
        raise RuntimeError("Telegram returned an unexpected QR login state")

    deep_link = "tg://login?token=" + base64.urlsafe_b64encode(token.token).decode().rstrip("=")
    image = qrcode.make(deep_link)
    path = _qr_path(user_id)
    image.save(path)
    return {
        "client": client,
        "qr_path": path,
        "token": token.token,
        "expires": int(token.expires),
        "deep_link": deep_link,
        "user_id": user_id,
    }


async def wait_for_qr_login(client: PyroClient, timeout: int = 300) -> str:
    """Wait for Telegram's updateLoginToken, then complete the QR login.

    The verification code is never collected in the bot chat. The user confirms
    the QR request inside their already-authorized Telegram app.
    """
    loop = asyncio.get_running_loop()
    completed: asyncio.Future[str] = loop.create_future()

    async def raw_handler(_client, update, _users, _chats):
        if not isinstance(update, UpdateLoginToken) or completed.done():
            return
        try:
            result = await _export(client)
            if isinstance(result, auth_types.LoginTokenSuccess):
                # Once Telegram returns loginTokenSuccess, this connection is
                # authorized and Pyrogram can export the authenticated session.
                session = await client.export_session_string()
                if not completed.done():
                    completed.set_result(session)
            elif isinstance(result, auth_types.LoginTokenMigrateTo):
                if not completed.done():
                    completed.set_exception(
                        RuntimeError(
                            f"Telegram requested a data-center migration to DC {result.dc_id}; retry the QR login."
                        )
                    )
        except Exception as exc:
            if not completed.done():
                completed.set_exception(exc)

    handler_ref = client.add_handler(RawUpdateHandler(raw_handler), group=-100)
    try:
        return await asyncio.wait_for(completed, timeout=timeout)
    finally:
        try:
            client.remove_handler(*handler_ref)
        except Exception:
            pass
