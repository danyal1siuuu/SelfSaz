# SelfSaz QR + Dashboard Fix

1. Replace `host_bot/bot.py`.
2. Add `core/telegram_login.py`.
3. Replace `core/plans.py` and `database/db.py` from the matching complete build.
4. Restart the app/service.

Login now uses Telegram QR authorization instead of collecting Telegram login codes in the bot chat. This avoids the `code was previously shared` failure.

The dashboard now includes Account, Invite Friends, and Daily Reward shortcuts. Inline keyboard buttons are normalized to Telegram native `primary`, `success`, and `danger` styles and each is placed on its own row for readability.
