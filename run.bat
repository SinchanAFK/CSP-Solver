@echo off
rem Starts the CSP map colouring website on http://localhost:8000
cd /d "%~dp0"
start "" http://localhost:8000
python app.py
pause
