@echo off
:: API detach restart
:: NOTE: timeout コマンドはコンソールが必要なため DETACHED_PROCESS では使用不可。
::       代わりに ping でウェイトする。CREATE_NO_WINDOW で起動すること。

:: 3 秒待機（4 回の応答 ≒ 3 秒）
ping -n 4 127.0.0.1 > nul

cd /d C:\01_Develop\project\kblite

:: Kill LISTENING process on port 8080 (PowerShell で確実に LISTEN 行だけを対象にする)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

:: 2 秒待機
ping -n 3 127.0.0.1 > nul

:: Kill again if still running
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

:: 1 秒待機
ping -n 2 127.0.0.1 > nul

:: Restart server
:: Prefer project venv; fall back to PATH `python`
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
start "KBLite Server" /B "%PYTHON_EXE%" -m uvicorn app:app --host 0.0.0.0 --port 8080
