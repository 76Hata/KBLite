@echo off
chcp 65001 >nul
:: API detach restart - wait before killing
timeout /t 3 /nobreak >nul

cd /d C:\01_Develop\project\kblite

:: Kill process using port 8080 (try multiple times for reliability)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr /R ":8080[ \t]"') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: Wait for process to terminate
timeout /t 2 /nobreak >nul

:: Kill again if still running
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr /R ":8080[ \t]"') do (
    taskkill /PID %%a /F >nul 2>&1
)

timeout /t 1 /nobreak >nul

:: Restart server
:: Prefer project venv; fall back to PATH `python`
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
start "KBLite Server" /B "%PYTHON_EXE%" -m uvicorn app:app --host 0.0.0.0 --port 8080
