# SelfSaz – Admin/Button QA

Date: 2026-09-24

## Static checks
- Python compileall: PASS
- Inline callback buttons found in `host_bot/bot.py`: 222 literal callbacks
- 208 handled directly in `host_bot/bot.py`
- 14 delegated callbacks are handled by `core/plans.py` / shared handlers:
  - `menu_account`, `menu_plans`, `menu_invite`, `menu_daily`
  - `menu_rates`, `refresh_rates`
  - `clean_10`, `clean_30`, `clean_60`
  - `auto_greet_toggle`, `auto_save_toggle`, `auto_typing_toggle`
  - `plan_validity_status`, `plan_validity_refresh`

## Real-operation fixes in this release
- Admin media broadcast now uses Telegram `copyMessage` and actually sends the selected media.
- Admin forward-all now accepts the next forwarded message and copies it to registered users.
- Global pin now executes Telegram `pinChatMessage` against the supplied chat/message IDs.
- Connection sync now really removes disconnected clients from `ACTIVE_CLIENTS` instead of always reporting zero.
- Broken-session cleanup now attempts a real Pyrogram session validation before removing invalid stored sessions.
- Registration, maintenance, anti-spam, deleted-message logger, max self count and support URL are persisted in `system_settings`.
- Global settings are reloaded on every update so a Railway restart does not silently reset them.
- User analytics now use persistent `created_at` and `last_seen_at` fields instead of row-id estimates.
- Login success metrics have persistent counters/timestamps.
- Upgrade/reward analytics use stored DB/Audit data where available.
- Stale inline callbacks remain subject to registration and plan-expiry server-side checks.

## Important runtime limitation
A static audit cannot prove Telegram-side permissions, Bot API credentials, Pyrogram session validity, or third-party service availability. Those must be tested on the deployed Railway service.
