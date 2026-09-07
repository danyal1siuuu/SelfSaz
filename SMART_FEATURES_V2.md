# SelfSaz Smart Features V2

## AI configuration on Railway
Set these environment variables:
- `AI_API_KEY` = your provider API key
- `AI_BASE_URL` = the OpenAI-compatible API root, for example `https://api.openai.com/v1`
- `AI_MODEL` = a model name supported by your provider, for example `gpt-4o-mini`

The admin panel can override `AI_MODEL` and `AI_BASE_URL` at runtime without storing the API key.

## What the AI now does
- The AI secretary no longer responds only to “سلام”. Every eligible incoming private message can be processed.
- Short conversation memory is stored per user in SQLite and can be turned off or cleared.
- `.هوش ...` asks the AI directly from the selfbot.
- `.خلاصه` summarizes a replied-to message.
- `.ترجمه انگلیسی` (or another target language) translates a replied-to message.
- The secretary has configurable cooldown and an admin-controlled default prompt.

## Other new selfbot features
- Fixed auto-reply with custom text and per-user cooldown.
- Away/busy mode with custom text.
- Automatic read marking for incoming private messages.
- Personal notes: `.یادداشت`, `.یادداشت‌ها`, `.حذف یادداشت‌ها`.
- Incoming/outgoing/AI/auto-reply activity counters.

## Admin controls
A new section `۱۳. هوش مصنوعی و امکانات هوشمند` exposes:
- global smart features on/off
- global AI on/off
- AI model
- AI Base URL
- default assistant prompt
- AI cooldown
- default auto-reply
- AI usage statistics
- AI connection test
- clear all AI memory
- smart feature usage counts
- reset smart settings

## Safety / privacy
Never put `AI_API_KEY` or a Telegram session string into the Telegram chat. Keep them in Railway Environment Variables / private server configuration.
