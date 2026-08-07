@echo off
REM ============================================================
REM  NewsAnalytics AI - Local Windows Launcher
REM  Double-click this file to run the app. First run sets up a
REM  virtual environment and installs dependencies automatically;
REM  every run after that starts in a few seconds.
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist venv (
    echo [Setup] First run detected - creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo [ERROR] Python was not found. Install Python 3.10-3.12 from
        echo         https://www.python.org/downloads/ and make sure
        echo         "Add python.exe to PATH" is checked during install.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

echo [Setup] Checking dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check

echo.
echo [Run] Starting NewsAnalytics AI...
echo [Run] Using local Ollama at http://localhost:11434 for AI.
echo [Run] Your browser will open automatically. Close this window to stop the app.
echo.
streamlit run streamlit_app.py --server.port 8765

pause
