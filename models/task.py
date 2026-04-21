"""タスクドメインモデル — 型・定数・バリデーション例外を定義する。

Service 層はここで定義された定数とバリデータを使って入力を検証する。
Store 層（sqlite_store / stores.task_mixin）はこのファイルを参照しない。
"""

from __future__ import annotations

from typing import Any, TypedDict

# ── 許可値定数 ──────────────────────────────────────────────────
VALID_STATUSES: tuple[str, ...] = ("todo", "in_progress", "done", "cancelled")
VALID_PRIORITIES: tuple[str, ...] = ("low", "normal", "high")
VALID_SCOPES: tuple[str, ...] = ("session", "global")
VALID_SOURCES: tuple[str, ...] = ("manual", "todowrite", "mcp")

DEFAULT_PRIORITY = "normal"
DEFAULT_SCOPE = "global"
DEFAULT_SOURCE = "manual"


# ── TypedDict（Store が返す dict 構造） ─────────────────────────
class TaskNote(TypedDict):
    id: str
    task_id: str
    note: str
    created_at: str


class Task(TypedDict, total=False):
    id: str
    title: str
    description: str
    status: str
    priority: str
    session_id: str | None
    source: str
    scope: str
    todo_key: str | None
    created_at: str
    updated_at: str
    due_date: str | None
    completed_at: str | None
    notes: list[TaskNote]


# ── ドメイン例外 ────────────────────────────────────────────────
class TaskError(Exception):
    """タスク操作に関する基底例外。"""


class TaskValidationError(TaskError):
    """入力バリデーションに失敗した場合に送出される。"""


class TaskNotFoundError(TaskError):
    """指定された task_id が存在しない場合に送出される。"""


# ── 入力バリデーション ──────────────────────────────────────────
def require_title(raw: Any) -> str:
    title = str(raw or "").strip()
    if not title:
        raise TaskValidationError("title は必須です")
    return title


def require_note(raw: Any) -> str:
    note = str(raw or "").strip()
    if not note:
        raise TaskValidationError("note は必須です")
    return note


def coerce_priority(raw: Any) -> str:
    value = str(raw or "").strip() or DEFAULT_PRIORITY
    return value if value in VALID_PRIORITIES else DEFAULT_PRIORITY


def coerce_scope(raw: Any) -> str:
    value = str(raw or "").strip() or DEFAULT_SCOPE
    return value if value in VALID_SCOPES else DEFAULT_SCOPE


def coerce_source(raw: Any) -> str:
    value = str(raw or "").strip() or DEFAULT_SOURCE
    return value if value in VALID_SOURCES else DEFAULT_SOURCE


def validate_status(raw: Any) -> str:
    value = str(raw or "").strip()
    if value not in VALID_STATUSES:
        raise TaskValidationError(f"status は {'/'.join(VALID_STATUSES)} のいずれかです")
    return value
