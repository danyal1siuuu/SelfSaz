# -*- coding: utf-8 -*-
"""Shared YouTube downloader used by both the selfbot plugin and host bot."""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any

import yt_dlp


def _find_result_files(prefix: str) -> list[str]:
    candidates = []
    for path in glob.glob(f"{prefix}*"):
        if os.path.isfile(path) and not path.endswith((".part", ".ytdl", ".tmp")):
            candidates.append(path)
    return sorted(candidates, key=os.path.getmtime, reverse=True)


def cleanup_prefix(prefix: str) -> None:
    for path in glob.glob(f"{prefix}*"):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass


def is_youtube_url(url: str) -> bool:
    value = (url or "").lower()
    return value.startswith(("http://", "https://")) and ("youtube.com/" in value or "youtu.be/" in value)


def _opts(outtmpl: str, max_mb: int | None) -> dict[str, Any]:
    # This is the same general selector yt-dlp documents as its default.
    # It is safer than hard-coding ext=mp4/m4a because those exact formats
    # are not guaranteed to exist for every YouTube item.
    opts: dict[str, Any] = {
        "format": "bv*+ba/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "overwrites": True,
        "restrictfilenames": False,
    }
    # max_filesize is only an early rejection optimization. Final size is
    # always checked after muxing because the combined output can be larger.
    if max_mb is not None:
        opts["max_filesize"] = int(max_mb * 1024 * 1024)
    return opts


def download_youtube(url: str, output_prefix: str, max_mb: int | None) -> dict[str, Any]:
    """Download one YouTube item and enforce final output size after merging."""
    Path(output_prefix).parent.mkdir(parents=True, exist_ok=True)
    cleanup_prefix(output_prefix)

    with yt_dlp.YoutubeDL(_opts(f"{output_prefix}%(id)s.%(ext)s", max_mb)) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("ویدیو قابل دریافت نیست یا اطلاعات آن استخراج نشد.")

    files = _find_result_files(output_prefix)
    if not files:
        raise RuntimeError("فایل خروجی دانلود پیدا نشد.")

    target = files[0]
    final_size = os.path.getsize(target)
    if max_mb is not None and final_size > max_mb * 1024 * 1024:
        cleanup_prefix(output_prefix)
        raise ValueError("MAX_SIZE")

    return {
        "path": target,
        "size": final_size,
        "size_mb": final_size / (1024 * 1024),
        "title": info.get("title") or "YouTube Video",
        "id": info.get("id") or "unknown",
    }


def human_error(exc: Exception, max_mb: int | None) -> str:
    text = str(exc).strip()
    low = text.lower()
    if isinstance(exc, ValueError) and text == "MAX_SIZE":
        limit = "نامحدود" if max_mb is None else f"{max_mb} مگابایت"
        return f"❌ حجم خروجی از سقف پلن شما ({limit}) بیشتر است."
    if "requested format is not available" in low:
        return (
            "❌ فرمت موجود برای این ویدیو با انتخاب‌گر فعلی قابل دریافت نیست. "
            "موتور دانلود به انتخاب‌گر عمومی `bv*+ba/best` منتقل شده؛ "
            "در صورت تداوم خطا، ویدیو احتمالاً محدود/خصوصی است یا یوتیوب آن را از این سرور ارائه نمی‌کند."
        )
    if "sign in to confirm" in low or "confirm you’re not a bot" in low or "confirm you're not a bot" in low:
        return "❌ یوتیوب برای این ویدیو احراز هویت/تأیید ضدربات می‌خواهد و دانلود بدون نشست معتبر ممکن نیست."
    if "private video" in low:
        return "❌ این ویدیو خصوصی است و بدون دسترسی مناسب قابل دانلود نیست."
    if "members-only" in low:
        return "❌ این ویدیو فقط برای اعضای کانال قابل مشاهده است."
    if "ffmpeg" in low:
        return "❌ برای ترکیب صدای جداگانه و تصویر، FFmpeg روی سرور باید فعال باشد."
    return f"❌ خطا در پردازش یوتیوب:\n`{text[:900]}`"
