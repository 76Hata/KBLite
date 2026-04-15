@echo off
:: APIからデタッチ起動される場合、レスポンス送信まで少し待機
timeout /t 3 /nobreak >nul

cd /d C:\01_Develop\project\kblite

:: ポート8780を使用しているプロセスを終了
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8780 "') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: プロセス終了を待機
timeout /t 2 /nobreak >nul

:: サーバーを再起動
start "KBLite Server" /B "C:\Users\76Hata\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn app:app --host 0.0.0.0 --port 8780
