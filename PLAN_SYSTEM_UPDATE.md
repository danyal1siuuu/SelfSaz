# SelfSaz — Plan & YouTube Update

## What changed

The subscription system is now centralized in `core/plans.py`.
The YouTube downloader is centralized in `core/youtube.py`.
`host_bot/bot.py` only contains a small integration layer for the dashboard/callbacks and the user-facing YouTube flow.

## Plan tiers

| Plan | YouTube limit | Friends | Enemies | Fonts | Cleaner minimum | AI secretary | Delete/edit logger | Daily coins |
|---|---:|---:|---:|---:|---:|---|---|---:|
| Normal | 100 MB | 3 | 3 | 2 | 60s | No | No | 5 |
| Iron | 250 MB | 5 | 5 | 3 | 30s | No | Yes | 10 |
| Bronze | 500 MB | 15 | 15 | 5 | 20s | No | Yes | 25 |
| Silver | 1 GB | 40 | 40 | 7 | 10s | Yes | Yes | 50 |
| Gold | 2 GB | 100 | 100 | 10 | 5s | Yes | Yes | 100 |
| Diamond | Unlimited at plan level | 9999 | 9999 | 10 | 1s | Yes | Yes | 250 |

The Diamond YouTube limit is represented by `None`, not an artificial numeric cap.

## Files to replace/add

Replace:

- `core/plans.py`
- `database/db.py`
- `host_bot/bot.py`
- `plugins/media_tools.py`
- `plugins/enemy_friend.py`
- `plugins/cleaner_tools.py`
- `plugins/deletelog_antiedit.py`
- `plugins/timename_bio.py`
- `plugins/monshi_ai.py`

Add:

- `core/youtube.py`
- `PLAN_SYSTEM_UPDATE.md`

## Important behavior

- Existing users keep their coins and plan when they reconnect. The old `INSERT OR REPLACE` reset behavior was removed.
- Legacy `is_vip=1` users are normalized to Diamond.
- Admin VIP grant/revoke is connected to the new plan engine.
- Cleaner timer, relation lists, clock fonts, AI secretary, delete/edit logger and YouTube download now honor plan limits.
- The YouTube format selector uses `bv*+ba/best`, which is yt-dlp's documented general best-available selector.
- Final output size is checked after download/merge, so the plan limit applies to the actual resulting file.
- Diamond has no plan-level YouTube size cap.
- For the Bot API path, Telegram currently documents a 50 MB limit for bot video uploads. For files above that, the host bot tries to send through the user's active selfbot client instead.

## Deployment

1. Replace the listed files and add `core/youtube.py`.
2. Keep the existing `.env` / Railway variables unchanged.
3. Restart the service once so `init_db()` runs the database migration.
4. No manual SQL migration is required.

The Dockerfile/Nixpacks configuration already installs FFmpeg, so YouTube video/audio merging is supported in the current deployment setup.
