@echo off
title RAG Stop All

echo Stopping services...

tasklist /FI "IMAGENAME eq node.exe" /FO TABLE | find /I "node.exe" >nul 2>&1
if %errorlevel% equ 0 (
    taskkill /F /IM node.exe >nul 2>&1
    echo [OK] Node stopped (frontend)
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
echo [OK] Port 8000 cleared (backend)

echo All services stopped.
pause
