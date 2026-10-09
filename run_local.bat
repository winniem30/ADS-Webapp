@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (echo Run setup_windows.bat first.& exit /b 1)
call ".venv\Scripts\activate.bat"
set FLASK_ENV=development
waitress-serve --listen=127.0.0.1:5000 app:app
