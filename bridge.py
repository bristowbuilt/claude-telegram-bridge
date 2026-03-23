#!/usr/bin/env python3
"""
Telegram → Claude Code bridge
Uses your Claude.ai subscription via the `claude` CLI — no separate API costs.

Setup:
  pip install python-telegram-bot
  set TELEGRAM_BOT_TOKEN=your_token
  set TELEGRAM_ALLOWED_IDS=your_telegram_user_id  (get it from /start)
  python bridge.py
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_IDS_RAW = os.environ.get("TELEGRAM_ALLOWED_IDS", "")
ALLOWED_IDS: set[int] = {int(x) for x in ALLOWED_IDS_RAW.split(",") if x.strip()}
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", Path.home() / "projects"))
HISTORY_FILE = Path(__file__).parent / "history.json"
MAX_HISTORY = 30        # messages to keep per chat (user+assistant pairs)
CLAUDE_TIMEOUT = 180    # seconds per request
# ─────────────────────────────────────────────────────────────────────────────

history: dict[str, list[dict]] = {}

def find_claude() -> str:
    """Find the claude CLI, checking common install locations on Windows."""
    found = shutil.which("claude")
    if found:
        return found
    # npm global bin on Windows
    npm_path = Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd"
    if npm_path.exists():
        return str(npm_path)
    return "claude"  # fallback, let it fail with a clear error

def load_history():
    global history
    if HISTORY_FILE.exists():
        history = json.loads(HISTORY_FILE.read_text())

def save_history():
    HISTORY_FILE.write_text(json.dumps(history, indent=2))

def is_allowed(user_id: int) -> bool:
    return not ALLOWED_IDS or user_id in ALLOWED_IDS

def build_prompt(chat_id: str, new_message: str) -> str:
    msgs = history.get(chat_id, [])[-MAX_HISTORY:]
    if not msgs:
        return new_message
    lines = []
    for m in msgs:
        prefix = "Human" if m["role"] == "user" else "Assistant"
        lines.append(f"{prefix}: {m['content']}")
    lines.append(f"Human: {new_message}")
    lines.append("Assistant:")
    return "\n\n".join(lines)

async def run_claude(prompt: str, cwd: Path) -> str:
    loop = asyncio.get_event_loop()
    def _run():
        return subprocess.run(
            [find_claude(), "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=str(cwd),
        )
    try:
        result = await loop.run_in_executor(None, _run)
        out = result.stdout.strip()
        if not out and result.stderr:
            return f"⚠️ Error: {result.stderr[:500]}"
        return out or "(no response)"
    except subprocess.TimeoutExpired:
        return "⏱ Timed out. Try a shorter request."
    except FileNotFoundError:
        return "❌ `claude` CLI not found. Is Claude Code installed and in PATH?"

async def send_long(update: Update, text: str):
    """Send a message, splitting at 4096 chars if needed."""
    for i in range(0, len(text), 4096):
        await update.message.reply_text(text[i:i + 4096])

# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"👋 Claude Code bridge is live.\n"
        f"Your Telegram user ID: `{uid}`\n\n"
        f"Commands:\n"
        f"/clear — wipe conversation memory\n"
        f"/cd <folder> — switch project folder (default: ~/projects)\n"
        f"/pwd — show current project folder",
        parse_mode="Markdown",
    )

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    cid = str(update.effective_chat.id)
    history[cid] = []
    save_history()
    await update.message.reply_text("🗑 Conversation cleared.")

async def cmd_pwd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    cid = str(update.effective_chat.id)
    cwd = ctx.chat_data.get("cwd", str(PROJECTS_DIR))
    await update.message.reply_text(f"📁 `{cwd}`", parse_mode="Markdown")

async def cmd_cd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: /cd <folder>")
        return
    target = Path(args[0]).expanduser()
    if not target.is_absolute():
        current = Path(ctx.chat_data.get("cwd", str(PROJECTS_DIR)))
        target = current / target
    if target.is_dir():
        ctx.chat_data["cwd"] = str(target)
        await update.message.reply_text(f"📁 Now in `{target}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Not a directory: `{target}`", parse_mode="Markdown")

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("🚫 Unauthorized.")
        return

    cid = str(update.effective_chat.id)
    user_msg = update.message.text
    cwd = Path(ctx.chat_data.get("cwd", str(PROJECTS_DIR)))

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    prompt = build_prompt(cid, user_msg)
    response = await run_claude(prompt, cwd)

    # Update history
    if cid not in history:
        history[cid] = []
    history[cid].append({"role": "user", "content": user_msg})
    history[cid].append({"role": "assistant", "content": response})
    # Trim
    history[cid] = history[cid][-(MAX_HISTORY * 2):]
    save_history()

    await send_long(update, response)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("ERROR: Set the TELEGRAM_BOT_TOKEN environment variable.")
        sys.exit(1)

    load_history()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("pwd", cmd_pwd))
    app.add_handler(CommandHandler("cd", cmd_cd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"✅ Bridge running | projects dir: {PROJECTS_DIR}")
    if ALLOWED_IDS:
        print(f"   Allowed user IDs: {ALLOWED_IDS}")
    else:
        print("   ⚠️  No TELEGRAM_ALLOWED_IDS set — anyone can message the bot!")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
