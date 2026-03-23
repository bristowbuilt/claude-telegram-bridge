@echo off
REM ── Claude Telegram Bridge ──────────────────────────────────────────────────
REM Edit these values before running:

set TELEGRAM_BOT_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE
set TELEGRAM_ALLOWED_IDS=PASTE_YOUR_TELEGRAM_USER_ID_HERE
set PROJECTS_DIR=%USERPROFILE%\projects
set PATH=%APPDATA%\npm;%PATH%

py bridge.py
pause
