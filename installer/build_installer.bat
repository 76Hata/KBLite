@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo  KBLite インストーラー ビルドスクリプト
echo ============================================================
echo.

:: スクリプトのディレクトリ（installer/）
set INSTALLER_DIR=%~dp0
:: プロジェクトルート（kblite/）
set PROJECT_DIR=%INSTALLER_DIR%..\
set BUILD_DIR=%INSTALLER_DIR%build
set DIST_DIR=%INSTALLER_DIR%dist
set SOURCE_COPY_DIR=%INSTALLER_DIR%source

:: ---- 事前チェック ----
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python が見つかりません。Python 3.10 以上をインストールしてください。
    pause
    exit /b 1
)

:: Python バージョン確認
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [INFO] Python バージョン: %PY_VER%

:: ---- PyInstaller インストール確認 ----
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller をインストールしています...
    python -m pip install pyinstaller --quiet
    if errorlevel 1 (
        echo [ERROR] PyInstaller のインストールに失敗しました。
        pause
        exit /b 1
    )
)
echo [INFO] PyInstaller: OK

:: ---- source/ ディレクトリにKBLiteファイルをコピー ----
echo.
echo [INFO] KBLite ソースファイルをコピーしています...

if exist "%SOURCE_COPY_DIR%" (
    rmdir /s /q "%SOURCE_COPY_DIR%"
)
mkdir "%SOURCE_COPY_DIR%"

:: コピー対象ファイル・ディレクトリ
set ITEMS=app.py app-config.json prompt.py sqlite_store.py deps.py statusline.py requirements.txt index.html mcp_tasks.py

for %%i in (%ITEMS%) do (
    if exist "%PROJECT_DIR%%%i" (
        copy /Y "%PROJECT_DIR%%%i" "%SOURCE_COPY_DIR%\%%i" >nul
        echo   コピー: %%i
    ) else (
        echo   スキップ（存在しない）: %%i
    )
)

:: ディレクトリのコピー
for %%d in (routes stores static commands services models) do (
    if exist "%PROJECT_DIR%%%d" (
        xcopy /E /I /Y /Q "%PROJECT_DIR%%%d" "%SOURCE_COPY_DIR%\%%d" >nul
        echo   コピー: %%d\
    )
)

echo [INFO] ソースコピー完了

:: ---- Step1: アンインストーラーを先にビルド ----
echo.
echo [INFO] アンインストーラーをビルドしています...
echo       （しばらくお待ちください）
echo.

cd /d "%INSTALLER_DIR%"

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "KBLite_Uninstall" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%" ^
    --clean ^
    --noconfirm ^
    kblite_uninstaller.py

if errorlevel 1 (
    echo.
    echo [ERROR] アンインストーラーのビルドに失敗しました。
    pause
    exit /b 1
)

if exist "%DIST_DIR%\KBLite_Uninstall.exe" (
    echo [INFO] KBLite_Uninstall.exe ビルド成功
) else (
    echo [ERROR] KBLite_Uninstall.exe が生成されませんでした。
    pause
    exit /b 1
)

:: ---- Step2: インストーラーをビルド（アンインストーラーを同梱）----
echo.
echo [INFO] インストーラーをビルドしています...
echo       （アンインストーラーを同梱します。しばらくお待ちください）
echo.

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "KBLite_Setup" ^
    --add-data "source;source" ^
    --add-data "%DIST_DIR%\KBLite_Uninstall.exe;." ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%" ^
    --specpath "%BUILD_DIR%" ^
    --clean ^
    --noconfirm ^
    kblite_installer.py

if errorlevel 1 (
    echo.
    echo [ERROR] ビルドに失敗しました。上記のエラーを確認してください。
    pause
    exit /b 1
)

if exist "%DIST_DIR%\KBLite_Setup.exe" (
    echo [INFO] KBLite_Setup.exe ビルド成功
) else (
    echo [ERROR] KBLite_Setup.exe が生成されませんでした。
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  ビルド成功！
echo  インストーラー : %DIST_DIR%\KBLite_Setup.exe
echo  アンインストーラー: %DIST_DIR%\KBLite_Uninstall.exe
echo.
echo  KBLite_Setup.exe のみ配布すれば OK です。
echo  （アンインストーラーが同梱されています）
echo ============================================================
echo.

pause
endlocal
