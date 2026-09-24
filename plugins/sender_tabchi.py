# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client, enums
from pyrogram.types import Message
from core.filters import self_cmd

BANNER = None

@Client.on_message(self_cmd(["پیام فرستنده"]))
async def set_banner(client: Client, message: Message):
    global BANNER
    if not message.reply_to_message:
        return await message.edit_text("❌ روی پیام مورد نظر ریپلای کنید.")
    BANNER = message.reply_to_message
    await message.edit_text("✅ بنر تبلیغاتی با موفقیت ست شد.")

@Client.on_message(self_cmd(["فرستنده"]))
async def send_to_online(client: Client, message: Message):
    global BANNER
    if not BANNER:
        return await message.edit_text("❌ ابتدا بنر را با `.پیام فرستنده` تنظیم کنید.")
    await message.edit_text("🚀 ارسال به افراد آنلاین گروه آغاز شد...")
    count = 0
    async for member in client.get_chat_members(message.chat.id):
        if member.user.is_bot or member.user.is_self:
            continue
        if member.user.status in [enums.UserStatus.ONLINE, enums.UserStatus.RECENTLY]:
            try:
                await BANNER.copy(member.user.id)
                count += 1
                await asyncio.sleep(4)
            except Exception:
                pass
    await message.reply_text(f"🏁 به {count} کاربر آنلاین ارسال گردید.")
