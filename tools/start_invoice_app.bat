@echo off
setlocal

cd /d "%~dp0\.."

if exist "app\windows\PDF发票自动整理归纳工具\PDF发票自动整理归纳工具.exe" (
    start "" "app\windows\PDF发票自动整理归纳工具\PDF发票自动整理归纳工具.exe"
    exit /b 0
)

if exist ".venv_windows\Scripts\python.exe" (
    start "" ".venv_windows\Scripts\python.exe" main.py
    exit /b 0
)

if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" main.py
    exit /b 0
)

start "" python main.py
exit /b 0
