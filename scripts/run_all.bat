@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title RAG-KB-System

echo ============================================
echo   RAG KB System - Local Startup
echo ============================================
echo.

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

echo [1/5] Checking .env config...
if not exist ".env" (
    echo [ERROR] .env not found in project root!
    echo        Run: copy .env.local .env
    pause
    exit /b 1
)
echo [OK] .env found

echo.
echo [2/5] MySQL should be running on port 3306.
netstat -an | findstr ":3306 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] MySQL detected on port 3306
) else (
    echo [WARN] MySQL NOT detected on port 3306 - check if it is running!
)

echo.
echo [3/5] Milvus Standalone should be on port 19530.
netstat -an | findstr ":19530 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Milvus detected on port 19530
) else (
    echo [WARN] Milvus NOT detected on port 19530 - check if it is running!
)

echo.
echo [4/5] Starting backend (new window will open)...
start "RAG-Backend" cmd /c "call scripts\run_backend.bat"
echo Waiting for backend to start...
timeout /t 10 /nobreak >nul 2>&1

curl -s http://localhost:8000/api/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend is responding at http://localhost:8000
) else (
    echo [WARN] Backend may still be starting or failed to start
    echo       Check the RAG-Backend window for details
)

echo.
echo [5/5] Starting frontend (new window will open)...
start "RAG-Frontend" cmd /c "call scripts\run_frontend.bat"

echo.
echo ============================================
echo   All launch commands sent!
echo ============================================
echo.
echo   Two NEW windows should have opened:
echo     1. RAG-Backend  - Python/Uvicorn backend
echo     2. RAG-Frontend - Vite dev server
echo.
echo   Backend API:   http://localhost:8000
echo   API Docs:      http://localhost:8000/docs
echo   Frontend URL:  see RAG-Frontend window
echo                  usually http://localhost:5173 or 5174
echo.
echo   Login:         admin / admin123
echo.
echo   If a window closes immediately, there was an error.
echo   Re-run this script to see error messages.
echo.
pause
