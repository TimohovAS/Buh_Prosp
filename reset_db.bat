@echo off
cd /d "%~dp0"
venv\Scripts\python.exe reset_db.py
pause
