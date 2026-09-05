# -*- coding: utf-8 -*-
import re

async def parse_agentic_command(text: str):
    clean = text.replace(".سلف", "").strip()
    patterns = [
        (r"(پاکسازی|حذف|دیلیت).*دشمن", "clearenemy", ""),
        (r"(افزودن|اضافه).*دشمن\s+(.*)", "addenemy", r"\2"),
        (r"(افزودن|اضافه).*دوست\s+(.*)", "addfriend", r"\2"),
        (r"(دانلود|دان).*یوتیوب\s+(.*)", "yt", r"\2"),
        (r"(میو|پیشی).*روشن", "meow_on", ""),
        (r"(حذف|بردار).*بک گراند", "removebg", ""),
        (r"(قیمت|نرخ).*ارز", "rates", "")
    ]
    for pattern, cmd, arg in patterns:
        m = re.search(pattern, clean)
        if m:
            return cmd, re.sub(pattern, arg, clean).strip()
    return "unknown", ""
