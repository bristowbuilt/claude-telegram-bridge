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
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_IDS_RAW = os.environ.get("TELEGRAM_ALLOWED_IDS", "")
ALLOWED_IDS: set[int] = {int(x) for x in ALLOWED_IDS_RAW.split(",") if x.strip()}
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", Path.home() / "projects"))
SESSIONS_FILE = Path(__file__).parent / "sessions.json"
CLAUDE_TIMEOUT = 180    # seconds per request
# ─────────────────────────────────────────────────────────────────────────────

sessions: dict[str, str] = {}  # chat_id -> claude session_id

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

def load_sessions():
    global sessions
    if SESSIONS_FILE.exists():
        sessions = json.loads(SESSIONS_FILE.read_text())

def save_sessions():
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))

def load_memory(cwd: Path) -> str:
    """Load memory files relevant to the current working directory."""
    base = Path.home() / ".dotfiles" / "claude" / "memory"
    if not base.exists():
        return ""

    # Always load global context
    files = [
        base / "global" / "george.md",
        base / "global" / "reminders.md",
    ]

    # Load project-specific memory based on cwd
    cwd_str = str(cwd).lower()
    if "trainheroic" in cwd_str:
        files += [
            base / "trainheroic" / "clients.md",
            base / "trainheroic" / "exercise-ids.md",
        ]
    elif "triathlon" in cwd_str:
        files += [
            base / "triathlon" / "system.md",
            base / "triathlon" / "athlete-profile.md",
        ]

    chunks = [f.read_text(encoding="utf-8") for f in files if f.exists()]
    return "\n\n---\n\n".join(chunks).strip()

def is_allowed(user_id: int) -> bool:
    return not ALLOWED_IDS or user_id in ALLOWED_IDS

async def run_claude(chat_id: str, message: str, cwd: Path) -> str:
    loop = asyncio.get_event_loop()
    session_id = sessions.get(chat_id)

    def _run():
        cmd = [find_claude(), "-p", message, "--output-format", "json"]
        if session_id:
            cmd += ["--resume", session_id]
        memory = load_memory(cwd)
        if memory:
            cmd += ["--append-system-prompt", memory]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=str(cwd),
        )
    try:
        logging.info(f"[{chat_id}] -> Claude | cwd: {cwd} | msg: {message[:80]}")
        result = await loop.run_in_executor(None, _run)
        if result.returncode != 0:
            err = result.stderr[:300]
            logging.error(f"[{chat_id}] Claude error: {err}")
            # Stale session — retry without resume
            if session_id and "no conversation found" in err.lower():
                logging.info(f"[{chat_id}] Stale session, retrying fresh")
                sessions.pop(chat_id, None)
                save_sessions()
                return await run_claude(chat_id, message, cwd)
            return f"Error: {err}"
        data = json.loads(result.stdout)
        new_session_id = data.get("session_id")
        if new_session_id:
            sessions[chat_id] = new_session_id
            save_sessions()
        response = data.get("result") or "(no response)"
        logging.info(f"[{chat_id}] <- Claude | {len(response)} chars | session: {new_session_id}")
        return response
    except subprocess.TimeoutExpired:
        logging.warning(f"[{chat_id}] Claude timed out")
        return "Timed out. Try a shorter request."
    except FileNotFoundError:
        logging.error("claude CLI not found")
        return "claude CLI not found. Is Claude Code installed and in PATH?"
    except json.JSONDecodeError:
        logging.error(f"[{chat_id}] Bad JSON from Claude: {result.stdout[:200]}")
        return result.stdout.strip() or "(no response)"

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
    sessions.pop(cid, None)
    save_sessions()
    await update.message.reply_text("Conversation cleared.")

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

    logging.info(f"[{cid}] {update.effective_user.username or update.effective_user.id}: {user_msg[:80]}")
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    response = await run_claude(cid, user_msg, cwd)

    await send_long(update, response)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("ERROR: Set the TELEGRAM_BOT_TOKEN environment variable.")
        sys.exit(1)

    load_sessions()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("pwd", cmd_pwd))
    app.add_handler(CommandHandler("cd", cmd_cd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"[OK] Bridge running | projects dir: {PROJECTS_DIR}")
    if ALLOWED_IDS:
        print(f"   Allowed user IDs: {ALLOWED_IDS}")
    else:
        print("   [WARN] No TELEGRAM_ALLOWED_IDS set -- anyone can message the bot!")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
