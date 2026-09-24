# -*- coding: utf-8 -*-
import os
import subprocess
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd

@Client.on_message(self_cmd(["round", "ویدیو گرد", "تلسکوپ"]))
async def video_note_creator(client: Client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.video:
        return await message.edit_text("❌ لطفاً روی یک ویدیو ریپلای کنید.")
    await message.edit_text("⏳ در حال تبدیل ویدیو به فرمت گرد (ویدیو نوت)...")
    raw = await message.reply_to_message.download()
    out = f"downloads/round_{message.id}.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", raw,
        "-vf", "crop=min(iw\\,ih):min(iw\\,ih),scale=400:400",
        "-c:v", "libx264", "-crf", "26", "-c:a", "aac",
        "-t", "60", out
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        await client.send_video_note(message.chat.id, out)
        await message.delete()
    except Exception as e:
        await message.edit_text(f"❌ خطا در پردازش با ffmpeg:\n`{e}`")
    finally:
        for f in [raw, out]:
            if os.path.exists(f):
                os.remove(f)
