# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import aiohttp
from config import AI_API_KEY, AI_BASE_URL
from core.plans import has_feature

# ثبت در گروه مستقل ۲ برای اجرای پایدار
@Client.on_message(filters.private & ~filters.me, group=2)
async def monshi_responder(client: Client, message: Message):
    # بررسی فعال بودن منشی روی اکانت سلف
    if not getattr(client, "monshi_active", False):
        return
    if not await has_feature(client.me.id, "ai_monshi"):
        return

    # نادیده گرفتن ربات‌ها و پیام‌های خود اکانت
    if not message.from_user or message.from_user.is_self or message.from_user.is_bot:
        return

    # دوستان ویژه معاف از منشی هستند
    if hasattr(client, "friends_set") and message.from_user.id in client.friends_set:
        return

    # تایمر هوشمند بین پیام‌ها (کاهش به ۱۰ ثانیه تا بشود با آن چت کرد)
    if not hasattr(client, "monshi_replied_users"):
        client.monshi_replied_users = {}

    user_id = message.from_user.id
    now = asyncio.get_event_loop().time()
    last_replied = client.monshi_replied_users.get(user_id, 0)
    
    # اگر فاصله پیام کمتر از ۱۰ ثانیه بود صبر کند تا اسپم نشود
    if now - last_replied < 10:
        return

    client.monshi_replied_users[user_id] = now
    
    # پیام پیش‌فرض در صورت در دسترس نبودن هوش مصنوعی
    default_text = getattr(client, "monshi_custom_text", "") or "سلام دوست عزیز؛ در حال حاضر آنلاین نیستم. به محض ورود پیامتان را می‌خوانم. 🙏"
    reply_text = default_text

    # اگر کلید هوش مصنوعی در متغیرهای ریلوی ست شده باشد:
    if AI_API_KEY:
        try:
            # زمان انتظار کافی (۱۵ ثانیه) برای دریافت پاسخ هوش مصنوعی
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "شما منشی و دستیار هوشمند تلگرام من هستید. "
                                "صاحب این اکانت هم‌اکنون آنلاین نیست یا مشغول است. "
                                "وظیفه شما این است که با مخاطب با کمال ادب، محبت، صمیمیت و بسیار کوتاه و مختصر صحبت کنید. "
                                "به سوالاتش پاسخ بدهید، با او احوال‌پرسی کنید و بگویید که پیامش را به صاحب اکانت می‌رسانید."
                            )
                        },
                        {"role": "user", "content": message.text or "سلام"}
                    ],
                    "max_tokens": 150
                }
                headers = {
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json"
                }
                async with session.post(f"{AI_BASE_URL}/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ai_reply = data["choices"][0]["message"]["content"].strip()
                        reply_text = f"🤖 **[منشی هوشمند]**\n\n{ai_reply}"
                    else:
                        err_body = await resp.text()
                        print(f"[!] AI API Error (Status {resp.status}): {err_body}")
        except Exception as e:
            print(f"[!] AI Connection Error: {e}")

    try:
        await message.reply_text(reply_text)
        print(f"[🤖 منشی سلف] به مخاطب {user_id} پاسخ داده شد.")
    except Exception as e:
        print(f"[!] خطا در ارسال پیام منشی: {e}")
