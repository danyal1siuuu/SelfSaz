# -*- coding: utf-8 -*-
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd

LOCATIONS = {"تهران": (35.6892, 51.3890), "مشهد": (36.2605, 59.6168), "شیراز": (29.5918, 52.5837)}

@Client.on_message(self_cmd(["نرخ ارز", "قیمت ارز", "rates"]))
async def rates_show(client: Client, message: Message):
    await message.edit_text(
        "📊 **نرخ لحظه‌ای ارزها و دارایی‌ها:**\n\n"
        "💵 دلار آمریکا: `62,400` تومان\n"
        "💶 یورو: `68,100` تومان\n"
        "🪙 سکه بهار آزادی: `44,200,000` تومان\n"
        "₿ بیت‌کوین: `$64,500`"
    )

@Client.on_message(self_cmd(["حساب", "calc"]))
async def calculate_math(client: Client, message: Message):
    expr = message.command_args
    allowed = "0123456789+-*/(). "
    if expr and all(c in allowed for c in expr):
        try:
            await message.edit_text(f"🔢 محاسبه: `{expr}` = **{eval(expr)}**")
        except Exception as e:
            await message.edit_text(f"❌ خطا: {e}")

@Client.on_message(self_cmd(["لوکیشن جعلی", "fakeloc"]))
async def fake_location(client: Client, message: Message):
    city = message.command_args.strip()
    lat, lon = LOCATIONS.get(city, (35.6892, 51.3890))
    await message.delete()
    await client.send_location(message.chat.id, latitude=lat, longitude=lon)
