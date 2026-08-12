@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title RAG-Backend

cd /d "%~dp0..\backend"

echo ============================================
echo   RAG KB System - Backend Server
echo ============================================
echo.

echo [Check] Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Install Python 3.11+
    pause
    exit /b 1
)
python --version

echo.
echo [Env] Checking .env in project root...
if not exist "%~dp0..\.env" (
    echo [WARN] No .env file found. Using defaults or env vars.
)

echo.
echo [Venv] Creating virtual environment...
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo.
echo [Deps] Installing requirements...
pip install -q -r requirements.txt

echo.
echo [Dirs] Creating data directories...
if not exist "data\uploads" mkdir data\uploads
if not exist "data\crawls" mkdir data\crawls
if not exist "logs" mkdir logs

echo.
echo ============================================
echo   Starting FastAPI server...
echo ============================================
echo.
echo   URL: http://localhost:8000
echo   Docs: http://localhost:8000/docs
echo.
echo   Press Ctrl+C to stop
echo ============================================

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
