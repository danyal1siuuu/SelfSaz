# -*- coding: utf-8 -*-
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from core.filters import self_cmd

CLEANER = {"active": False, "delay": 20, "pv": True, "group": False}

@Client.on_message(self_cmd(["حذف کن"]))
async def auto_clean_config(client: Client, message: Message):
    args = message.command_args.split()
    if not args:
        st = "فعال ✅" if CLEANER["active"] else "غیرفعال ❌"
        return await message.edit_text(f"وضعیت حذف خودکار: {st}\nتاخیر: `{CLEANER['delay']}` ثانیه")
    if args[0] == "روشن":
        CLEANER["active"] = True
        await message.edit_text("✅ حذف خودکار پیام‌ها روشن شد.")
    elif args[0] == "خاموش":
        CLEANER["active"] = False
        await message.edit_text("🛑 حذف خودکار خاموش شد.")
    elif args[0] == "تنظیم" and len(args) > 1 and args[1].isdigit():
        CLEANER["delay"] = int(args[1])
        await message.edit_text(f"⏱ تاخیر به `{args[1]}` ثانیه تغییر یافت.")

@Client.on_message(filters.me)
async def auto_clean_runner(client: Client, message: Message):
    if not CLEANER["active"]:
        return
    if (message.chat.type.value == "private" and CLEANER["pv"]) or (message.chat.type.value in ["group", "supergroup"] and CLEANER["group"]):
        await asyncio.sleep(CLEANER["delay"])
        try:
            await message.delete()
        except Exception:
            pass
