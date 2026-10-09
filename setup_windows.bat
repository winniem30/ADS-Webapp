@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul || (echo Python launcher not found. Install Python 3.11+ and add it to PATH.& exit /b 1)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo Setup complete. Configure .env if needed, then run run_local.bat.
