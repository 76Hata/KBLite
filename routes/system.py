"""システム系エンドポイント — ヘルスチェック・設定・Rate Limits"""
import json
import os
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
