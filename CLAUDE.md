# claude-telegram-bridge

A Telegram bot that bridges messages to the Claude Code CLI (`claude`). Send a message to a private Telegram bot → it runs `claude` as a subprocess → returns the response. Uses your existing Claude.ai subscription, no separate API cost.

## What this project does

- Telegram bot with access control (allowlist by user ID)
- Routes messages to the local `claude` CLI with conversation history context
- Supports `/cd` to switch working directory per chat session
- Persists conversation history across restarts (`history.json`)

## Stack

- Python 3, async (`asyncio`)
- `python-telegram-bot` >=21.0
- Runs Claude via `subprocess` (not the API)
- Node.js required (for `claude` CLI installation)

## Key files

```
bridge.py          # Everything: bot handlers, Claude invocation, history management
start.bat          # Windows launcher — sets env vars and starts bridge.py
history.json       # Per-chat conversation history (auto-managed, gitignored)
SETUP.md           # Full setup guide
requirements.txt
```

## Config (env vars)

| Var | Purpose |
|-----|---------|
| `TELEGRAM_BOT_TOKEN` | From BotFather |
| `TELEGRAM_ALLOWED_IDS` | Comma-separated Telegram user IDs (whitelist) |
| `PROJECTS_DIR` | Base dir for `/cd` navigation (default: `~/projects`) |

## Code conventions

- Fully async — all handlers are `async def`, blocking Claude calls use `run_in_executor`
- `find_claude()` searches PATH + `%APPDATA%\npm` for the `claude` binary (Windows-aware)
- History trimmed to last 30 message pairs (`MAX_HISTORY = 30`)
- Responses >4096 chars are split into multiple Telegram messages
- Claude invoked with `--output-format text`
- Timeout: 180 seconds per Claude call
- Section headers use `# ── Name ────...` style

## Bot commands

- `/start` — show bot info and caller's user ID
- `/clear` — wipe conversation history for this chat
- `/cd <folder>` — change working directory (persists per chat)
- `/pwd` — show current working directory
- Any other text → sent to Claude as a prompt

## Security

Unauthorized users get a silent "🚫 Unauthorized" response. Never add user IDs to the allowlist without verifying identity.
