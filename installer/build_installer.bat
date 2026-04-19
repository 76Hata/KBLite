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
for %%d in (routes stores static commands) do (
    if exist "%PROJECT_DIR%%%d" (
        xcopy /E /I /Y /Q "%PROJECT_DIR%%%d" "%SOURCE_COPY_DIR%\%%d" >nul
        echo   コピー: %%d\
    )
)

echo [INFO] ソースコピー完了

:: ---- PyInstaller でビルド ----
echo.
echo [INFO] インストーラーをビルドしています...
echo       （しばらくお待ちください）
echo.

cd /d "%INSTALLER_DIR%"

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "KBLite_Setup" ^
    --add-data "source;source" ^
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

:: ---- ビルド後の確認 ----
if exist "%DIST_DIR%\KBLite_Setup.exe" (
    echo.
    echo ============================================================
    echo  ビルド成功！
    echo  出力: %DIST_DIR%\KBLite_Setup.exe
    echo ============================================================
    echo.
    echo KBLite_Setup.exe を配布してください。
    echo （PyInstaller の環境がない PC でも実行できます）
    echo.
) else (
    echo [ERROR] KBLite_Setup.exe が生成されませんでした。
    pause
    exit /b 1
)

pause
endlocal
