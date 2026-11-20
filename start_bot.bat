@echo off
title Biruktawit Fikre Workout Bot Runner
echo ========================================================
echo  BIRUKTAWIT FIKRE (@GIBDAW) // WORKOUT BOT ENGINE
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/3] Verifying environment & static assets...
python scripts\verify_setup.py

echo.
echo [2/3] Checking dependencies...
python -c "import aiogram, asyncpg, pydantic_settings; print('Dependencies OK')" 2>nul
if errorlevel 1 (
    echo Installing dependencies from requirements.txt...
    pip install -r requirements.txt
)

echo.
echo [3/3] Starting Telegram Bot Engine...
python bot.py
pause

