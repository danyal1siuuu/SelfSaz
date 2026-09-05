# -*- coding: utf-8 -*-
import aiohttp
from datetime import datetime
import pytz
from pyrogram import Client
from pyrogram.types import Message
from core.filters import self_cmd

async def fetch_live_market_data():
    """استعلام واقعی و زنده نرخ‌ها از وب‌سرویس نوبیتکس و کوین‌گکو"""
    rates = {
        "usdt_toman": "درحال اتصال...",
        "btc_usd": "---",
        "eth_usd": "---",
        "ton_usd": "---",
        "trx_usd": "---",
        "time": ""
    }
    tz = pytz.timezone("Asia/Tehran")
    rates["time"] = datetime.now(tz).strftime("%H:%M:%S")

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        # ۱. نرخ لحظه‌ای تتر به تومان (نوبیتکس)
        try:
            async with session.get("https://api.nobitex.ir/v2/orderbook/USDTIRT") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = int(data.get("lastTradePrice", 0))
                    # در نوبیتکس قیمت‌های IRT در صورت ریال بودن تقسیم بر 10 یا به تومان است
                    rates["usdt_toman"] = f"{price:,}"
        except Exception:
            rates["usdt_toman"] = "درحال بررسی"

        # ۲. نرخ بیت‌کوین و سایر ارزها
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,the-open-network,tron&vs_currencies=usd"
            async with session.get(url) as resp:
                if resp.status == 200:
                    cdata = await resp.json()
                    rates["btc_usd"] = f"{int(cdata.get('bitcoin', {}).get('usd', 0)):,}"
                    rates["eth_usd"] = f"{int(cdata.get('ethereum', {}).get('usd', 0)):,}"
                    rates["ton_usd"] = f"{cdata.get('the-open-network', {}).get('usd', 0):.2f}"
                    rates["trx_usd"] = f"{cdata.get('tron', {}).get('usd', 0):.3f}"
        except Exception:
            pass

    return rates

def format_market_display(rates: dict) -> str:
    return (
        "📈 **تابلو نرخ لحظه‌ای بازار و رمزارزها**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **تتر (دلار آزاد):** `{rates['usdt_toman']}` تومان\n"
        f"🪙 **بیت‌کوین (BTC):** `${rates['btc_usd']}`\n"
        f"💎 **اتریوم (ETH):** `${rates['eth_usd']}`\n"
        f"💎 **تون‌کوین (TON):** `${rates['ton_usd']}`\n"
        f"⚡️ **ترون (TRX):** `${rates['trx_usd']}`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 استعلام به وقت تهران: `{rates['time']}`\n"
        "⚡️ _منبع: وب‌سرویس مستقیم مارکت رسمی صرافی نوبیتکس_"
    )

@Client.on_message(self_cmd(["rates", "نرخ ارز"]))
async def rates_show(client: Client, message: Message):
    await message.edit_text("⏳ در حال دریافت نرخ لحظه‌ای...")
    data = await fetch_live_market_data()
    await message.edit_text(format_market_display(data))
