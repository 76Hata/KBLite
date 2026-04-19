"""システム系エンドポイント — ヘルスチェック・設定・Rate Limits"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from deps import (
    AI_SERVICES,
    CATEGORIES,
    MODELS,
    TEAMS,
    WORKSPACE_PROJECTS,
    _INDEX_HTML_PATH,
    resolve_project_cwd,
    store,
)


def _workspace_projects_with_resolved_cwd() -> list[dict]:
    enriched: list[dict] = []
    for p in WORKSPACE_PROJECTS:
        entry = dict(p)
        pid = str(p.get("id") or "")
        entry["resolved_cwd_claude"] = resolve_project_cwd(pid, "claude")
        entry["resolved_cwd_cursor"] = resolve_project_cwd(pid, "cursor")
        enriched.append(entry)
    return enriched


_RATE_LIMITS_PATH = Path(os.getenv("SQLITE_PATH", str(Path(__file__).parent.parent / "data" / "sqlite" / "kblite.db"))).parent / "rate-limits.json"


async def index(request: Request) -> HTMLResponse:
    return HTMLResponse(_INDEX_HTML_PATH.read_text(encoding="utf-8"))


async def get_app_config(request: Request) -> JSONResponse:
    return JSONResponse({
        "categories": CATEGORIES,
        "teams": TEAMS,
        "models": MODELS,
        "ai_services": AI_SERVICES,
        "workspace_projects": _workspace_projects_with_resolved_cwd(),
    })


async def get_rate_limits(request: Request) -> JSONResponse:
    if not _RATE_LIMITS_PATH.is_file():
        return JSONResponse({"error": "not_available"}, status_code=404)
    try:
        data = json.loads(_RATE_LIMITS_PATH.read_text(encoding="utf-8"))
        return JSONResponse(data)
    except (json.JSONDecodeError, OSError):
        return JSONResponse({"error": "read_error"}, status_code=500)


async def health(request: Request) -> JSONResponse:
    sqlite_ok = store.sqlite_healthcheck()
    return JSONResponse(
        {"status": "ok" if sqlite_ok else "degraded", "sqlite": "ok" if sqlite_ok else "error"},
        status_code=200 if sqlite_ok else 503,
    )


async def restart_server(request: Request) -> JSONResponse:
    """サーバーを自己再起動する（デタッチしたバッチプロセス経由）"""
    app_dir = Path(__file__).parent.parent
    bat_path = app_dir / "restart.bat"
    port = 8080

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        ["cmd", "/c", str(bat_path)],
        cwd=str(app_dir),
        close_fds=True,
        creationflags=creationflags,
    )

    return JSONResponse({"status": "restarting", "port": port})


def _is_subpath(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


async def open_file(request: Request) -> JSONResponse:
    """指定パスのファイルを OS 既定の関連付けアプリで開く。

    許可ルート: プロジェクトルート配下 および ~/.claude/ 配下のみ。
    それ以外は 403 を返す。
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    raw_path = str(data.get("path") or "").strip()
    if not raw_path:
        return JSONResponse({"error": "path_required"}, status_code=400)

    try:
        target = Path(raw_path).expanduser().resolve(strict=False)
    except Exception as e:
        return JSONResponse({"error": "invalid_path", "detail": str(e)}, status_code=400)

    project_root = Path(__file__).parent.parent.resolve()
    home_claude = (Path.home() / ".claude").resolve()
    allowed_roots = [project_root, home_claude]

    if not any(_is_subpath(target, root) for root in allowed_roots):
        return JSONResponse(
            {
                "error": "forbidden_path",
                "detail": "Only project root and ~/.claude are allowed",
                "path": str(target),
            },
            status_code=403,
        )

    if not target.exists():
        return JSONResponse({"error": "not_found", "path": str(target)}, status_code=404)

    # プラットフォーム別に既定アプリでファイルを開く。
    # Windows では VS Code (code --reuse-window) を最優先してウィンドウを最前面に移動し、
    # VS Code がない場合は os.startfile → explorer.exe の順でフォールバックする。
    opened_via = None
    last_error: str | None = None
    try:
        if sys.platform == "win32":
            code_exe = shutil.which("code")
            if code_exe:
                # --reuse-window: 既存 VS Code ウィンドウを再利用してフォーカスを移す
                subprocess.Popen(
                    [code_exe, "--reuse-window", str(target)],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                opened_via = "vscode"
                # VS Code を最前面に移動（focus steal 防止を回避するため PowerShell 経由）
                ps_script = (
                    "Start-Sleep -Milliseconds 800;"
                    "$wsh = New-Object -ComObject WScript.Shell;"
                    "$procs = Get-Process -Name 'Code' -ErrorAction SilentlyContinue;"
                    "if ($procs) { $wsh.AppActivate($procs[0].Id) | Out-Null }"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                try:
                    os.startfile(str(target))  # type: ignore[attr-defined]
                    opened_via = "os.startfile"
                except OSError as e:
                    last_error = f"os.startfile failed: {e}"
                    subprocess.Popen(
                        ["explorer.exe", str(target)],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    opened_via = "explorer.exe"
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
            opened_via = "open"
        else:
            subprocess.Popen(["xdg-open", str(target)])
            opened_via = "xdg-open"
    except Exception as e:
        detail = f"{last_error + '; ' if last_error else ''}{e}"
        print(f"[open_file] FAILED path={target} detail={detail}", file=sys.stderr)
        return JSONResponse({"error": "open_failed", "detail": detail}, status_code=500)

    print(f"[open_file] OK via={opened_via} path={target}", file=sys.stderr)
    return JSONResponse({"status": "ok", "path": str(target), "via": opened_via})


async def debug_env(request: Request) -> JSONResponse:
    """デバッグ用: Claude CLI パス・イベントループ・環境情報を返す"""
    claude_path = shutil.which("claude")
    loop = asyncio.get_event_loop()
    return JSONResponse({
        "platform": sys.platform,
        "python_version": sys.version,
        "event_loop_type": type(loop).__name__,
        "claude_which": claude_path,
        "PATH": os.environ.get("PATH", ""),
        "sqlite_ok": store.sqlite_healthcheck(),
    })
