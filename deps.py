"""共有依存オブジェクト — store / config / logger を一元管理する"""

import json
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kblite")

# ファイルロギング追加（VPSからsshfs経由で確認可能）
_log_file = Path(__file__).parent / "kblite.log"
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger.addHandler(_file_handler)
logging.getLogger("uvicorn").addHandler(_file_handler)
logging.getLogger("uvicorn.error").addHandler(_file_handler)

from sqlite_store import SQLiteStore

logger.info("SQLiteStore を初期化中...")
store = SQLiteStore()

# ── 設定ファイル ──────────────────────────────────────────────────
_APP_CONFIG_PATH = Path(__file__).parent / "app-config.json"


def _load_app_config() -> dict:
    with open(_APP_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


_app_config = _load_app_config()

AGENTS = _app_config.get("agents", [])
_APP_COMMANDS_DIR = Path(__file__).parent / "commands"  # kblite/commands/（アプリ同梱・最優先）
_PROJECT_COMMANDS_DIR = Path(__file__).parent.parent / ".claude" / "commands"
_HOME_COMMANDS_DIR = Path.home() / ".claude" / "commands"
AGENT_COMMANDS_DIR = (
    _APP_COMMANDS_DIR
    if _APP_COMMANDS_DIR.is_dir()
    else _PROJECT_COMMANDS_DIR
    if _PROJECT_COMMANDS_DIR.is_dir()
    else _HOME_COMMANDS_DIR
)
CATEGORIES = _app_config.get("categories", [])
TEAMS = _app_config.get("teams", [])
MODELS = _app_config.get("models", [])
AI_SERVICES = _app_config.get(
    "ai_services",
    [{"id": "claude", "name": "Claude Code", "cli": "claude", "default": True}],
)
WORKSPACE_PROJECTS = _app_config.get("workspace_projects", [])
_PROJECT_CWD_MAP: dict[str, str] = {p["id"]: p.get("cwd", "") for p in WORKSPACE_PROJECTS}


def resolve_project_cwd(project_id: str, ai_service: str) -> str:
    """CLI 実行時の作業ディレクトリを解決する。"""
    base = _PROJECT_CWD_MAP.get(project_id, "")
    if not base:
        return ""
    if ai_service != "cursor":
        return base
    for p in WORKSPACE_PROJECTS:
        if p.get("id") != project_id:
            continue
        override = (p.get("cwd_cursor") or "").strip()
        if override:
            return override
        break
    if "/workspaces/" in base and "/workspaces-cursor/" not in base:
        return base.replace("/workspaces/", "/workspaces-cursor/", 1)
    return base


# ── 静的 HTML ─────────────────────────────────────────────────────
_INDEX_HTML_PATH = Path(__file__).parent / "index.html"
