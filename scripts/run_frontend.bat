@echo off
chcp 65001 >nul 2>&1

title RAG-Frontend

cd /d "%~dp0..\frontend"

echo ============================================
echo   RAG KB System - Frontend Dev Server
echo ============================================
echo.

echo [1/4] Checking Node.js...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found in PATH!
    echo.
    echo Please install Node.js 18+ from:
    echo   https://nodejs.org/
    echo.
    echo Or add Node.js to your system PATH.
    echo.
    pause
    exit /b 1
)
node --version
echo [OK] Node.js found

echo.
echo [2/4] Checking node_modules...
if not exist "node_modules\package.json" (
    echo       First time: running npm install...
    echo       This may take 3-5 minutes...
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed!
        pause
        exit /b 1
    )
) else (
    echo [OK] node_modules exists
)

echo.
echo [3/4] Checking if port 5173-5176 is free...
netstat -an | findstr ":5173 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARN] Port 5173 is occupied, Vite will auto-switch port
)
netstat -an | findstr ":5174 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARN] Port 5174 is occupied, Vite will auto-switch port
)
netstat -an | findstr ":5175 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARN] Port 5175 is occupied, Vite will auto-switch port
)
echo [OK] Port check done

echo.
echo [4/4] Starting Vite dev server...
echo   Press Ctrl+C to stop this server
echo   ============================================
echo.

call npx vite --host --port 5173

echo.
if %errorlevel% neq 0 (
    echo [ERROR] Vite exited with error code %errorlevel%
) else (
    echo Vite stopped cleanly.
)
pause
