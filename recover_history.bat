@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title Antigravity IDE History Recovery
cd /d "%~dp0"

echo ===================================================
echo   Antigravity IDE History Recovery
echo ===================================================

python antigravity_ide_history_recovery.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Script exited with code %ERRORLEVEL%]
    pause
)
