@echo off
chcp 65001 >nul
title 智慧親師通 - 伺服器啟動程式
echo =========================================
echo       智慧親師通 (Smart School System)
echo =========================================
echo.
echo [系統] 正在啟動虛擬環境與後台伺服器...
cd /d "%~dp0"

:: Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo [錯誤] 找不到虛擬環境 (.venv)，請先確認環境是否建置完成！
    pause
    exit /b
)

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Open browser automatically
echo [系統] 正在開啟打卡網頁...
start http://127.0.0.1:8000/static/swipe.html

:: Start FastAPI server
echo [系統] 伺服器啟動成功！請勿關閉此黑色視窗（若關閉將導致打卡機失效）。
echo.

:: Start Ngrok in a new window (Please replace YOUR_NGROK_DOMAIN with your actual static domain)
start cmd /k "ngrok http --domain=YOUR_NGROK_DOMAIN 8000"

uvicorn main:app --host 0.0.0.0 --port 8000

pause
