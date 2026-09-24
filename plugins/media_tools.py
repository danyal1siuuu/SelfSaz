# -*- coding: utf-8 -*-
import asyncio
import os
import qrcode
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd
from core.plans import get_user_yt_limit_mb
from core.youtube import cleanup_prefix, download_youtube, human_error

@Client.on_message(self_cmd(["yt", "ytdl", "یوتوب"]))
async def download_youtube_cmd(client: Client, message: Message):
    url = message.command_args
    if not url:
        return await message.edit_text("❌ لطفاً لینک یوتیوب را بعد از دستور وارد کنید.\nمثال: `.yt https://youtu.be/...`")
    max_mb = await get_user_yt_limit_mb(client.me.id)
    limit_text = "نامحدود" if max_mb is None else f"{max_mb} MB"
    prefix = f"downloads/yt_{message.id}_"
    await message.edit_text(f"⏳ در حال دانلود یوتیوب...\n📦 سقف پلن: `{limit_text}`")
    try:
        result = await asyncio.to_thread(download_youtube, url, prefix, max_mb)
        size_mb = result["size_mb"]
        await message.edit_text(f"📤 دانلود شد (`{size_mb:.1f} MB`)؛ در حال ارسال...")
        await client.send_video(message.chat.id, result["path"], caption=f"🎬 **{result['title']}**\n📦 حجم: `{size_mb:.1f} MB`\n⚡️ دانلود شده توسط سلف‌ساز")
        await message.delete()
    except Exception as e:
        await message.edit_text(human_error(e, max_mb))
    finally:
        cleanup_prefix(prefix)

@Client.on_message(self_cmd(["qr", "کیوآر"]))
async def create_qr(client: Client, message: Message):
    text = message.command_args
    if not text:
        return await message.edit_text("❌ متن یا لینکی وارد کنید.")
    img_path = f"downloads/qr_{message.id}.png"
    img = qrcode.make(text)
    img.save(img_path)
    await client.send_photo(message.chat.id, img_path, caption=f"🏁 کد QR برای:\n`{text}`")
    if os.path.exists(img_path):
        os.remove(img_path)
    await message.delete()
