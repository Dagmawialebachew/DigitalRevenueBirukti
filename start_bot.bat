@echo off
title Biruktawit Fikre Workout Bot Runner
echo ========================================================
echo  BIRUKTAWIT FIKRE (@GEBDAW) // WORKOUT BOT ENGINE
echo ========================================================
echo.

cd /d "%~dp0"

set "PYTHONUNBUFFERED=1"
set "PYTHON_EXE=C:\Users\kiruk\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [1/2] Verifying setup & static assets...
"%PYTHON_EXE%" scripts\verify_setup.py

echo.
echo [2/2] Starting Telegram Bot Engine (Auto-Reload on changes)...
"%PYTHON_EXE%" scripts\dev_reload.py
pause
