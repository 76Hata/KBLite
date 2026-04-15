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


_RATE_LIMITS_PATH = Path(os.getenv("SQLITE_PATH", str(Path(__file__).parent / "data" / "sqlite" / "kblite.db"))).parent / "rate-limits.json"


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
