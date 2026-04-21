"""Claude Code 権限管理エンドポイント

~/.claude/settings.json の permissions.allow / permissions.deny を
Web UI から CRUD 操作するための API。

また、AI エージェントが権限ブロックされたときに申請を投稿し、
ユーザーが KBLite UI から承認 / 拒否できる「権限申請ダイアログ」機能も提供する。
"""

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

# ── 権限申請キュー（インメモリ） ─────────────────────────────────────────
# 要素: {"id": str, "tool": str, "pattern": str, "reason": str, "ts": float}
_perm_requests: list[dict[str, Any]] = []

_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# 許可するパターンの最大長（DoS 対策）
_MAX_PATTERN_LEN = 500


def _read_settings() -> dict:
    """settings.json を読み取る。存在しない場合は空 dict を返す。"""
    try:
        if _SETTINGS_PATH.is_file():
            return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _write_settings(data: dict) -> None:
    """settings.json に書き戻す。"""
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _validate_pattern(pattern: str) -> str | None:
    """パターンの基本バリデーション。問題があればエラーメッセージを返す。"""
    if not pattern or not pattern.strip():
        return "pattern は空にできません"
    if len(pattern) > _MAX_PATTERN_LEN:
        return f"pattern が長すぎます（最大 {_MAX_PATTERN_LEN} 文字）"
    # 許可フォーマット例: Write(path/**), Read(path), Bash(cmd*), など
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*\(.+\)$|^\*$", pattern.strip()):
        return (
            "pattern は 'ToolName(path)' または 'ToolName(path/**)' の形式で入力してください。"
            " 例: Write(C:/Users/foo/.claude/skills/**)"
        )
    return None


async def get_permissions(request: Request) -> JSONResponse:
    """現在の Claude Code 権限リストを返す。

    Response:
        {
            "allow": ["Write(...)", ...],
            "deny":  ["Write(...)", ...]
        }
    """
    settings = _read_settings()
    perms = settings.get("permissions", {})
    return JSONResponse(
        {
            "allow": perms.get("allow", []),
            "deny": perms.get("deny", []),
        }
    )


async def add_permission(request: Request) -> JSONResponse:
    """allow または deny リストにパターンを追加する。

    Request body:
        {
            "list":    "allow" | "deny",
            "pattern": "Write(C:/Users/foo/.claude/skills/**)"
        }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    target_list = str(body.get("list", "allow")).strip()
    if target_list not in ("allow", "deny"):
        return JSONResponse({"error": "list は 'allow' または 'deny' を指定してください"}, status_code=400)

    pattern = str(body.get("pattern", "")).strip()
    err = _validate_pattern(pattern)
    if err:
        return JSONResponse({"error": err}, status_code=400)

    settings = _read_settings()
    perms = settings.setdefault("permissions", {})
    lst: list[str] = perms.setdefault(target_list, [])

    if pattern in lst:
        return JSONResponse(
            {"status": "already_exists", "allow": perms.get("allow", []), "deny": perms.get("deny", [])}
        )

    lst.append(pattern)
    try:
        _write_settings(settings)
    except OSError as e:
        return JSONResponse({"error": f"設定ファイルの書き込みに失敗しました: {e}"}, status_code=500)

    return JSONResponse(
        {
            "status": "added",
            "allow": perms.get("allow", []),
            "deny": perms.get("deny", []),
        }
    )


async def submit_permission_request(request: Request) -> JSONResponse:
    """AI エージェントが権限ブロックを受けたときに申請を投稿する。

    Request body:
        {
            "tool":    "Write",
            "pattern": "Write(C:/Users/foo/.claude/skills/**)",
            "reason":  "React+TypeScript スキルファイルを作成したい"  // optional
        }
    Response:
        {"id": "<uuid>", "status": "pending"}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    pattern = str(body.get("pattern", "")).strip()
    err = _validate_pattern(pattern)
    if err:
        return JSONResponse({"error": err}, status_code=400)

    req_id = str(uuid.uuid4())
    _perm_requests.append(
        {
            "id": req_id,
            "tool": str(body.get("tool", "")).strip(),
            "pattern": pattern,
            "reason": str(body.get("reason", "")).strip(),
            "ts": time.time(),
        }
    )
    return JSONResponse({"id": req_id, "status": "pending"}, status_code=201)


async def list_permission_requests(request: Request) -> JSONResponse:
    """未処理の権限申請一覧を返す。

    Response:
        {"requests": [{"id": ..., "tool": ..., "pattern": ..., "reason": ..., "ts": ...}, ...]}
    """
    return JSONResponse({"requests": list(_perm_requests)})


async def approve_permission_request(request: Request) -> JSONResponse:
    """権限申請を承認する（settings.json の allow リストに追加し、申請を削除する）。

    Path param: request_id
    """
    req_id = request.path_params.get("request_id", "")
    match = next((r for r in _perm_requests if r["id"] == req_id), None)
    if match is None:
        return JSONResponse({"error": "申請が見つかりません"}, status_code=404)

    pattern = match["pattern"]
    settings = _read_settings()
    perms = settings.setdefault("permissions", {})
    lst: list[str] = perms.setdefault("allow", [])
    if pattern not in lst:
        lst.append(pattern)
    try:
        _write_settings(settings)
    except OSError as e:
        return JSONResponse({"error": f"設定ファイルの書き込みに失敗しました: {e}"}, status_code=500)

    _perm_requests.remove(match)
    return JSONResponse(
        {
            "status": "approved",
            "pattern": pattern,
            "allow": perms.get("allow", []),
        }
    )


async def deny_permission_request(request: Request) -> JSONResponse:
    """権限申請を拒否する（申請をキューから削除するのみ）。

    Path param: request_id
    """
    req_id = request.path_params.get("request_id", "")
    match = next((r for r in _perm_requests if r["id"] == req_id), None)
    if match is None:
        return JSONResponse({"error": "申請が見つかりません"}, status_code=404)

    _perm_requests.remove(match)
    return JSONResponse({"status": "denied", "pattern": match["pattern"]})


async def remove_permission(request: Request) -> JSONResponse:
    """allow または deny リストからパターンを削除する。

    Request body:
        {
            "list":    "allow" | "deny",
            "pattern": "Write(C:/Users/foo/.claude/skills/**)"
        }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    target_list = str(body.get("list", "allow")).strip()
    if target_list not in ("allow", "deny"):
        return JSONResponse({"error": "list は 'allow' または 'deny' を指定してください"}, status_code=400)

    pattern = str(body.get("pattern", "")).strip()
    if not pattern:
        return JSONResponse({"error": "pattern は必須です"}, status_code=400)

    settings = _read_settings()
    perms = settings.get("permissions", {})
    lst: list[str] = perms.get(target_list, [])

    if pattern not in lst:
        return JSONResponse({"error": "指定されたパターンが見つかりません"}, status_code=404)

    lst.remove(pattern)
    perms[target_list] = lst
    settings["permissions"] = perms

    try:
        _write_settings(settings)
    except OSError as e:
        return JSONResponse({"error": f"設定ファイルの書き込みに失敗しました: {e}"}, status_code=500)

    return JSONResponse(
        {
            "status": "removed",
            "allow": perms.get("allow", []),
            "deny": perms.get("deny", []),
        }
    )
