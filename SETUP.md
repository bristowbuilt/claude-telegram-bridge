# Claude Telegram Bridge — Windows Setup

## What this is
A bridge that lets you talk to Claude Code on your Windows PC via Telegram.
Uses your existing Claude.ai subscription — no extra API costs.

---

## Step 1 — Install prerequisites on Windows

```powershell
# Install Node.js (for Claude Code)
winget install OpenJS.NodeJS.LTS

# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Install Python (if not already installed)
winget install Python.Python.3.12

# Install bridge dependencies
pip install python-telegram-bot
```

---

## Step 2 — Log in to Claude on Windows

```powershell
claude login
```
Follow the browser flow. This links to your Claude.ai subscription — same account, zero extra cost.

---

## Step 3 — Clone your projects

```powershell
mkdir %USERPROFILE%\projects
cd %USERPROFILE%\projects
git clone git@github.com:bristowbuilt/triathlon-program.git
git clone git@github.com:bristowbuilt/TrainHeroic-core.git
```

You'll also need to set up an SSH key on this machine for GitHub:
```powershell
ssh-keygen -t ed25519 -C "windows-desktop"
type %USERPROFILE%\.ssh\id_ed25519.pub
# Add that key to: https://github.com/settings/keys
```

---

## Step 4 — Restore project files not in git

These files are gitignored and need to be copied manually from your Mac:

**triathlon-program:**
- `.env` (has your Strava/Oura/Resend credentials)
- `triathlon.db` (your activity history)

Copy them to `%USERPROFILE%\projects\triathlon-program\`

---

## Step 5 — Create your Telegram bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Follow prompts, name it something like "Claude Desktop"
4. Copy the **bot token** it gives you

---

## Step 6 — Get your Telegram user ID

1. Message **@userinfobot** on Telegram
2. It will reply with your user ID (a number like `123456789`)

---

## Step 7 — Configure and run the bridge

Edit `start.bat` and fill in:
- `TELEGRAM_BOT_TOKEN` — from Step 5
- `TELEGRAM_ALLOWED_IDS` — your user ID from Step 6

Then double-click `start.bat` to run.

To auto-start on boot: add `start.bat` to Windows Startup folder
(`Win+R` → `shell:startup` → paste a shortcut there).

---

## Usage

| Command | What it does |
|---|---|
| Just type anything | Chat with Claude |
| `/clear` | Wipe conversation memory |
| `/cd triathlon-program` | Switch to that project folder |
| `/pwd` | Show current project folder |
| `/start` | Show your user ID |

---

## Transferring MyClaw state

The MyClaw OpenClaw instance has:
- `triathlon-program` cloned at `~/projects/triathlon-program`
- `.env` file with credentials (Strava token saved there after OAuth)
- `triathlon.db`

If you want that Strava refresh token, ask OpenClaw to paste the `.env` contents,
then save it locally.
