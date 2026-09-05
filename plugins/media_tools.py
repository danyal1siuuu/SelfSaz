# -*- coding: utf-8 -*-
import os
import glob
import qrcode
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd
from core.plans import get_user_yt_limit_mb
import yt_dlp

@Client.on_message(self_cmd(["yt", "ytdl", "یوتوب"]))
async def download_youtube(client: Client, message: Message):
    url = message.command_args
    if not url:
        return await message.edit_text("❌ لطفاً لینک یوتیوب را بعد از دستور وارد کنید.\nمثال: `.yt https://youtu.be/...`")
    
    await message.edit_text("🔍 در حال بررسی اطلاعات ویدیو و سطح دسترسی شما...")
    
    # استخراج سقف مجاز دانلود برای رتبه کاربر
    max_mb = await get_user_yt_limit_mb(client.me.id)
    max_bytes = max_mb * 1024 * 1024
    
    outtmpl = f'downloads/yt_{message.id}_%(id)s.%(ext)s'
    
    # اصلاح فرمت برای جلوگیری از خطای "Requested format is not available"
    opts = {
        'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b',
        'outtmpl': outtmpl,
        'merge_output_format': 'mp4',
        'max_filesize': max_bytes,
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        await message.edit_text(f"⏳ در حال دانلود از یوتیوب... (سقف مجاز رتبه شما: {max_mb} مگابایت)")
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'YouTube Video')
            
        # پیدا کردن فایل خروجی دقیق دانلود شده
        found_files = glob.glob(f"downloads/yt_{message.id}_*")
        if not found_files:
            return await message.edit_text("❌ فایلی برای ارسال یافت نشد.")
            
        target_file = found_files[0]
        f_size_mb = os.path.getsize(target_file) // (1024 * 1024)
        
        await message.edit_text(f"📤 دانلود با موفقیت انجام شد ({f_size_mb} MB)؛ در حال ارسال...")
        
        await client.send_video(
            chat_id=message.chat.id,
            video=target_file,
            caption=f"🎬 **{title}**\n📦 حجم: `{f_size_mb} MB`\n⚡️ دانلود شده توسط سلف‌ساز"
        )
        
        # پاکسازی پس از ارسال
        for f in found_files:
            if os.path.exists(f):
                os.remove(f)
                
        await message.delete()
        
    except yt_dlp.utils.MaxDownloadsReached:
        await message.edit_text(f"❌ حجم این ویدیو بیشتر از سقف رتبه شما ({max_mb} مگابایت) است! لطفاً پلن خود را ارتقا دهید.")
    except Exception as e:
        err_str = str(e)
        if "File is larger than max-filesize" in err_str or "larger than maximum allowed" in err_str.lower():
            await message.edit_text(f"❌ حجم این ویدیو فراتر از سقف مجاز پلن شما ({max_mb} مگابایت) است! برای افزایش سقف، در بات پلن خود را ارتقا دهید.")
        else:
            await message.edit_text(f"❌ خطا در پردازش یوتیوب:\n`{err_str}`")
        # پاکسازی در صورت بروز خطا
        for f in glob.glob(f"downloads/yt_{message.id}_*"):
            if os.path.exists(f):
                os.remove(f)

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
