@echo off
echo Starting AI Schematic Assistant Bridge...
echo.
echo Chrome will open automatically on claude.ai
echo Log in if needed, then leave this window open.
echo Press Ctrl+C to stop.
echo.
cd /d "%~dp0"
python bridge.py
pause
