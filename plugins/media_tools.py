# -*- coding: utf-8 -*-
import os
import qrcode
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd
import yt_dlp

@Client.on_message(self_cmd(["yt", "ytdl", "یوتوب"]))
async def download_youtube(client: Client, message: Message):
    url = message.command_args
    if not url:
        return await message.edit_text("❌ لینک یوتیوب را وارد کنید.")
    await message.edit_text("⏳ در حال دانلود از یوتیوب...")
    opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'max_filesize': 45 * 1024 * 1024
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fname = ydl.prepare_filename(info)
        await message.edit_text("📤 در حال ارسال ویدیو...")
        await client.send_video(message.chat.id, fname, caption=info.get('title', 'Video'))
        os.remove(fname)
        await message.delete()
    except Exception as e:
        await message.edit_text(f"❌ خطا: {e}")

@Client.on_message(self_cmd(["qr", "کیوآر"]))
async def create_qr(client: Client, message: Message):
    text = message.command_args
    if not text:
        return await message.edit_text("❌ متن یا لینکی وارد کنید.")
    img_path = "downloads/qr.png"
    img = qrcode.make(text)
    img.save(img_path)
    await client.send_photo(message.chat.id, img_path, caption=f"🏁 کد QR برای:
`{text}`")
    os.remove(img_path)
    await message.delete()
