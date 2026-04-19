#!/usr/bin/env python3
"""TodoWrite → KBLite DB 同期スクリプト

Claude Code の TodoWrite ツールが書き出す ``~/.claude/todos/<session_id>-agent-*.json``
を読み取り、KBLite の tasks テーブルに UPSERT する。

呼び出し方:
    # 全ての todo ファイルを走査して同期
    python scripts/sync_todowrite.py

    # 特定の todo ファイルだけ同期（PostToolUse hook から呼ぶ）
    python scripts/sync_todowrite.py --file "<path>"

    # Claude Code hook の JSON を stdin で受け取る
    python scripts/sync_todowrite.py --stdin

環境変数:
    SQLITE_PATH : KBLite の SQLite ファイルパス
                  （未指定なら kblite/data/sqlite/kblite.db）
    CLAUDE_TODOS_DIR : TodoWrite の JSON ディレクトリ
                  （未指定なら ~/.claude/todos）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path


# ── パス解決 ────────────────────────────────────────────────────────────

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "sqlite" / "kblite.db"
_DB_PATH = Path(os.getenv("SQLITE_PATH", str(_DEFAULT_DB)))
_TODOS_DIR = Path(os.getenv("CLAUDE_TODOS_DIR", str(Path.home() / ".claude" / "todos")))

# ファイル名例: "<session_id>-agent-<agent_id>.json"
_TODO_FILENAME_RE = re.compile(
    r"^(?P<session>[0-9a-fA-F-]{8,})-agent-(?P<agent>[0-9a-fA-F-]+)\.json$"
)


# ── TodoWrite JSON の正規化 ─────────────────────────────────────────────

_STATUS_MAP = {
    "pending": "todo",
    "in_progress": "in_progress",
    "completed": "done",
    "cancelled": "cancelled",
}


def _normalize_status(status: str) -> str:
    return _STATUS_MAP.get((status or "").strip(), "todo")


def _parse_session_id(path: Path) -> tuple[str | None, str | None]:
    m = _TODO_FILENAME_RE.match(path.name)
    if not m:
        return None, None
    return m.group("session"), m.group("agent")


def _load_todos(path: Path) -> list[dict]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return data


# ── DB 側（最小実装、kblite 本体の Mixin を import しない） ────────────

_TASK_DDL_CREATE = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    status      TEXT DEFAULT 'todo',
    priority    TEXT DEFAULT 'normal',
    session_id  TEXT DEFAULT NULL,
    source      TEXT DEFAULT 'manual',
    scope       TEXT DEFAULT 'global',
    todo_key    TEXT DEFAULT NULL,
    created_at  DATETIME DEFAULT (datetime('now','localtime')),
    updated_at  DATETIME DEFAULT (datetime('now','localtime')),
    due_date    DATETIME DEFAULT NULL,
    completed_at DATETIME DEFAULT NULL
);
"""


def _open_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    # 1) テーブルだけ先に作る
    conn.executescript(_TASK_DDL_CREATE)
    # 2) 既存DBに新列が無ければ ALTER TABLE で追加
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "source" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN source TEXT DEFAULT 'manual'")
    if "scope" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN scope TEXT DEFAULT 'global'")
    if "todo_key" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN todo_key TEXT DEFAULT NULL")
    # 3) 列が揃ってからインデックスを作る
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_todo_key "
        "ON tasks(todo_key) WHERE todo_key IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_scope_status ON tasks(scope, status)"
    )
    conn.commit()
    return conn


def _upsert_todowrite(conn: sqlite3.Connection, todo_key: str,
                      title: str, status: str,
                      session_id: str | None) -> str:
    """todo_key をキーに tasks を UPSERT する。戻り値は tasks.id"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    norm_status = _normalize_status(status)

    row = conn.execute(
        "SELECT id, status, completed_at FROM tasks WHERE todo_key = ?",
        (todo_key,),
    ).fetchone()

    if row is None:
        task_id = str(uuid.uuid4())
        completed_at = now if norm_status == "done" else None
        conn.execute(
            """INSERT INTO tasks (id, title, description, status, priority,
                                  session_id, source, scope, todo_key,
                                  created_at, updated_at, completed_at)
               VALUES (?, ?, '', ?, 'normal', ?, 'todowrite', 'session', ?,
                       ?, ?, ?)""",
            (task_id, title, norm_status, session_id, todo_key,
             now, now, completed_at),
        )
        return task_id

    prev_status = row["status"]
    completed_at = row["completed_at"]
    if norm_status == "done" and prev_status != "done":
        completed_at = now
    elif norm_status != "done":
        completed_at = None

    conn.execute(
        """UPDATE tasks
              SET title = ?, status = ?,
                  session_id = COALESCE(?, session_id),
                  updated_at = ?, completed_at = ?
            WHERE todo_key = ?""",
        (title, norm_status, session_id, now, completed_at, todo_key),
    )
    return row["id"]


# ── 同期本体 ────────────────────────────────────────────────────────────

def sync_file(path: Path, conn: sqlite3.Connection) -> int:
    """1ファイルを同期する。戻り値は処理した todo 件数。"""
    if not path.exists() or not path.is_file():
        return 0
    todos = _load_todos(path)
    if not todos:
        return 0

    session_id, _agent_id = _parse_session_id(path)
    count = 0
    for todo in todos:
        if not isinstance(todo, dict):
            continue
        todo_id = str(todo.get("id", "")).strip()
        content = str(todo.get("content", "")).strip()
        status = str(todo.get("status", "pending")).strip()
        if not todo_id or not content:
            continue
        # todo_key = session_id:todo_id（session不明なら agentファイル名stemにフォールバック）
        key_prefix = session_id or path.stem
        todo_key = f"{key_prefix}:{todo_id}"
        _upsert_todowrite(conn, todo_key, content, status, session_id)
        count += 1
    conn.commit()
    return count


def sync_all(conn: sqlite3.Connection) -> int:
    if not _TODOS_DIR.exists():
        return 0
    total = 0
    for path in _TODOS_DIR.glob("*.json"):
        total += sync_file(path, conn)
    return total


# ── hooks 入力パース（PostToolUse から stdin JSON で呼ばれる） ──────────

def _extract_path_from_hook_input(data: dict) -> Path | None:
    """Claude Code hook の stdin JSON から対象ファイルパスを推定する。

    TodoWrite hook のペイロード構造は将来変わりうるので、複数パターンを許容する。
    """
    # よくあるキーを順に探す
    candidates = []
    for key in ("tool_input", "input", "arguments", "params"):
        v = data.get(key)
        if isinstance(v, dict):
            for pk in ("file", "path", "file_path"):
                if pk in v and isinstance(v[pk], str):
                    candidates.append(v[pk])
    for pk in ("file", "path", "file_path"):
        if pk in data and isinstance(data[pk], str):
            candidates.append(data[pk])

    for p in candidates:
        try:
            path = Path(p)
            if path.exists():
                return path
        except Exception:
            continue
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync TodoWrite JSON to KBLite DB.")
    parser.add_argument("--file", help="同期する JSON ファイルパス")
    parser.add_argument("--stdin", action="store_true",
                        help="Claude Code hook の JSON を stdin で受け取る")
    parser.add_argument("--all", action="store_true",
                        help="~/.claude/todos/*.json を全て同期する（既定）")
    args = parser.parse_args(argv)

    try:
        conn = _open_db()
    except sqlite3.Error as e:
        # hook に失敗を伝搬させたくない（Claude の動作を止めない）
        print(f"[sync_todowrite] DB open error: {e}", file=sys.stderr)
        return 0

    total = 0
    stdin_had_path = False
    try:
        target_file: Path | None = None

        if args.file:
            target_file = Path(args.file)

        if args.stdin:
            try:
                raw = sys.stdin.read()
                if raw.strip():
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        p = _extract_path_from_hook_input(data)
                        if p is not None:
                            target_file = p
                            stdin_had_path = True
            except Exception:
                # stdin が壊れていても黙って fallback
                pass

        if target_file is not None:
            total = sync_file(target_file, conn)
            # ファイルが特定できた場合は、件数ゼロでも全件同期は避ける
        else:
            total = sync_all(conn)
    finally:
        conn.close()

    print(f"[sync_todowrite] synced {total} todo item(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
