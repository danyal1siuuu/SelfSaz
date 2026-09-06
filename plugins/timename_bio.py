# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd
from core.manager import FONTS, clean_profile_name
from core.plans import get_allowed_fonts

@Client.on_message(self_cmd(["timename start", "زمان اسم روشن"]))
async def start_time(client: Client, message: Message):
    args = message.command_args.split()
    name = args[0] if args else getattr(client, "original_name", None) or "Self"
    font = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
    allowed = await get_allowed_fonts(client.me.id)
    if font not in allowed:
        return await message.edit_text(f"🔒 فونت `{font}` برای پلن شما فعال نیست. فونت‌های مجاز: `{', '.join(map(str, allowed))}`")
    if getattr(client, "timename_active", False):
        return await message.edit_text("⚠️ ساعت در حال حاضر روشن است.")

    client.original_name = getattr(client, "original_name", None) or clean_profile_name(client.me.first_name)
    client.timename_active = True
    client.timename_base = name
    client.timename_font = font

    async def worker():
        last = ""
        while getattr(client, "timename_active", False):
            from datetime import datetime
            import pytz
            now = datetime.now(pytz.timezone("Asia/Tehran")).strftime("%H:%M")
            if now != last:
                last = now
                style = FONTS.get(client.timename_font, FONTS[1])
                clock = "".join(style.get(ch, ch) for ch in now)
                try:
                    await client.update_profile(first_name=f"{client.timename_base} {clock}"[:64])
                except Exception:
                    pass
            await asyncio.sleep(20)

    if getattr(client, "timename_task", None):
        client.timename_task.cancel()
    client.timename_task = asyncio.create_task(worker())
    await message.edit_text(f"🕒 ساعت فعال شد: `{name}` با فونت `{font}`")

@Client.on_message(self_cmd(["timename stop", "زمان اسم خاموش"]))
async def stop_time(client: Client, message: Message):
    client.timename_active = False
    task = getattr(client, "timename_task", None)
    if task:
        task.cancel()
        client.timename_task = None
    try:
        from core.manager import restore_original_name
        await restore_original_name(client)
    except Exception:
        pass
    await message.edit_text("🛑 ساعت خاموش شد و نام قبلی بازیابی شد.")
