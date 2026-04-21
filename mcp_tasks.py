#!/usr/bin/env python3
"""
KBLite タスク管理 MCP サーバー（stdio transport）

Claude Code から以下のコマンドで登録:
  claude mcp add kblite-tasks -- python C:/01_Develop/project/kblite/mcp_tasks.py

提供ツール:
  task_create        — タスクを作成する
  task_list          — タスク一覧を取得する（status でフィルタ可）
  task_update        — タスクのステータス・内容を更新する
  task_add_note      — タスクに作業メモを追加する
  task_delete        — タスクを削除する
  task_resume_context — 直近の未完了タスクと各ノートを返す（セッション再開用）
"""

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

# ── DB 接続 ──────────────────────────────────────────────────────────────────

_DB_PATH = os.getenv(
    "SQLITE_PATH",
    str(Path(__file__).parent / "data" / "sqlite" / "kblite.db"),
)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # テーブルが存在しない場合だけ作成（KBLite 本体と共有 DB なので冪等に）
    conn.executescript("""
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
        CREATE TABLE IF NOT EXISTS task_notes (
            id         TEXT PRIMARY KEY,
            task_id    TEXT NOT NULL,
            note       TEXT NOT NULL,
            created_at DATETIME DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
    """)
    # 既存DBの ALTER TABLE（冪等）
    existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "source" not in existing_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN source TEXT DEFAULT 'manual'")
    if "scope" not in existing_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN scope TEXT DEFAULT 'global'")
    if "todo_key" not in existing_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN todo_key TEXT DEFAULT NULL")
    # 列が揃ってからインデックスを作る
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_todo_key ON tasks(todo_key) WHERE todo_key IS NOT NULL"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_scope_status ON tasks(scope, status)")
    conn.commit()
    return conn


_conn = _get_conn()


# ── DB 操作ユーティリティ ────────────────────────────────────────────────────


def _row_to_task(row) -> dict:
    keys = row.keys() if hasattr(row, "keys") else []

    def _get(key, default=None):
        return row[key] if key in keys else default

    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"] or "",
        "status": row["status"],
        "priority": row["priority"],
        "session_id": row["session_id"] or None,
        "source": _get("source", "manual") or "manual",
        "scope": _get("scope", "global") or "global",
        "todo_key": _get("todo_key"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "due_date": row["due_date"] or None,
        "completed_at": row["completed_at"] or None,
    }


def _notes_for(task_id: str) -> list[dict]:
    rows = _conn.execute(
        "SELECT * FROM task_notes WHERE task_id = ? ORDER BY created_at ASC",
        (task_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── ツール実装 ───────────────────────────────────────────────────────────────


def tool_task_create(args: dict) -> str:
    title = str(args.get("title", "")).strip()
    if not title:
        return json.dumps({"error": "title は必須です"}, ensure_ascii=False)
    description = str(args.get("description", "")).strip()
    priority = args.get("priority", "normal")
    if priority not in ("low", "normal", "high"):
        priority = "normal"
    session_id = args.get("session_id") or None
    due_date = args.get("due_date") or None
    scope = args.get("scope") or "global"
    if scope not in ("session", "global"):
        scope = "global"
    source = args.get("source") or "manual"
    if source not in ("manual", "todowrite", "mcp"):
        source = "manual"

    task_id = str(uuid.uuid4())
    _conn.execute(
        """INSERT INTO tasks (id, title, description, priority, session_id, due_date,
                              scope, source)
           VALUES (?,?,?,?,?,?,?,?)""",
        (task_id, title, description, priority, session_id, due_date, scope, source),
    )
    _conn.commit()
    row = _conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    task = _row_to_task(row)
    return json.dumps({"ok": True, "task": task}, ensure_ascii=False)


def tool_task_list(args: dict) -> str:
    status = args.get("status") or None
    session_id = args.get("session_id") or None
    scope = args.get("scope") or None
    source = args.get("source") or None

    sql = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if session_id:
        sql += " AND session_id = ?"
        params.append(session_id)
    if scope:
        sql += " AND scope = ?"
        params.append(scope)
    if source:
        sql += " AND source = ?"
        params.append(source)
    sql += (
        " ORDER BY CASE status "
        "WHEN 'in_progress' THEN 0 "
        "WHEN 'todo' THEN 1 "
        "WHEN 'done' THEN 2 ELSE 3 END, updated_at DESC"
    )

    rows = _conn.execute(sql, params).fetchall()
    tasks = []
    for row in rows:
        t = _row_to_task(row)
        t["notes"] = _notes_for(t["id"])
        tasks.append(t)
    return json.dumps({"tasks": tasks}, ensure_ascii=False)


def tool_task_update(args: dict) -> str:
    task_id = str(args.get("task_id", "")).strip()
    if not task_id:
        return json.dumps({"error": "task_id は必須です"}, ensure_ascii=False)

    row = _conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        return json.dumps({"error": "タスクが見つかりません"}, ensure_ascii=False)

    allowed = {"title", "description", "status", "priority", "session_id", "due_date"}
    updates = {k: v for k, v in args.items() if k in allowed}
    if not updates:
        task = _row_to_task(row)
        task["notes"] = _notes_for(task_id)
        return json.dumps({"ok": True, "task": task}, ensure_ascii=False)

    if "status" in updates and updates["status"] not in ("todo", "in_progress", "done", "cancelled"):
        return json.dumps(
            {"error": "status は todo/in_progress/done/cancelled のいずれかです"}, ensure_ascii=False
        )

    if updates.get("status") == "done":
        updates["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif "status" in updates:
        updates["completed_at"] = None

    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]
    _conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
    _conn.commit()

    updated = _conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    task = _row_to_task(updated)
    task["notes"] = _notes_for(task_id)
    return json.dumps({"ok": True, "task": task}, ensure_ascii=False)


def tool_task_add_note(args: dict) -> str:
    task_id = str(args.get("task_id", "")).strip()
    note_text = str(args.get("note", "")).strip()
    if not task_id or not note_text:
        return json.dumps({"error": "task_id と note は必須です"}, ensure_ascii=False)

    if _conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone() is None:
        return json.dumps({"error": "タスクが見つかりません"}, ensure_ascii=False)

    note_id = str(uuid.uuid4())
    _conn.execute(
        "INSERT INTO task_notes (id, task_id, note) VALUES (?,?,?)",
        (note_id, task_id, note_text),
    )
    _conn.execute(
        "UPDATE tasks SET updated_at = datetime('now','localtime') WHERE id=?",
        (task_id,),
    )
    _conn.commit()
    row = _conn.execute("SELECT * FROM task_notes WHERE id=?", (note_id,)).fetchone()
    return json.dumps({"ok": True, "note": dict(row)}, ensure_ascii=False)


def tool_task_delete(args: dict) -> str:
    task_id = str(args.get("task_id", "")).strip()
    if not task_id:
        return json.dumps({"error": "task_id は必須です"}, ensure_ascii=False)
    cur = _conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    _conn.commit()
    if cur.rowcount == 0:
        return json.dumps({"error": "タスクが見つかりません"}, ensure_ascii=False)
    return json.dumps({"ok": True}, ensure_ascii=False)


def tool_task_resume_context(args: dict) -> str:
    """未完了タスク（todo/in_progress）とそのノートを返す。セッション再開時に使う。

    scope='global' のタスク（大きな案件・ユーザー追加分）を優先的に表示し、
    scope='session' のタスク（TodoWrite由来）は参考として別枠で表示する。
    """
    rows = _conn.execute(
        """SELECT * FROM tasks
           WHERE status IN ('todo','in_progress')
           ORDER BY CASE scope WHEN 'global' THEN 0 ELSE 1 END,
                    CASE status WHEN 'in_progress' THEN 0 ELSE 1 END,
                    updated_at DESC
           LIMIT 30""",
    ).fetchall()
    tasks = []
    for row in rows:
        t = _row_to_task(row)
        t["notes"] = _notes_for(t["id"])
        tasks.append(t)

    globals_ = [t for t in tasks if t.get("scope") == "global"]
    sessions_ = [t for t in tasks if t.get("scope") != "global"]

    def _fmt(t):
        lines = []
        badge = "[進行中]" if t["status"] == "in_progress" else "[未着手]"
        prio = {"high": "★高", "normal": "中", "low": "▽低"}.get(t["priority"], t["priority"])
        src = t.get("source") or "manual"
        lines.append(f"### {badge} {t['title']} (優先度:{prio} / source:{src})")
        lines.append(f"- ID: `{t['id']}`")
        if t["description"]:
            lines.append(f"- 内容: {t['description']}")
        if t["due_date"]:
            lines.append(f"- 期限: {t['due_date']}")
        if t["notes"]:
            lines.append("- メモ:")
            for n in t["notes"]:
                lines.append(f"  - [{n['created_at']}] {n['note']}")
        lines.append("")
        return lines

    if not tasks:
        summary = "現在、未完了タスクはありません。"
    else:
        out = []
        if globals_:
            out.append("## 未完了タスク（大きな案件 / scope=global）\n")
            for t in globals_:
                out.extend(_fmt(t))
        if sessions_:
            out.append("## セッション内タスク（TodoWrite由来 / scope=session）\n")
            for t in sessions_:
                out.extend(_fmt(t))
        summary = "\n".join(out)

    return json.dumps({"summary": summary, "tasks": tasks}, ensure_ascii=False)


# ── MCP プロトコル処理 ───────────────────────────────────────────────────────

TOOLS = {
    "task_create": {
        "description": "大きな案件・横断タスクを新規作成する（scope=global 既定）。セッション内の細かい進捗は TodoWrite を使うこと。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "タスクのタイトル（必須）"},
                "description": {"type": "string", "description": "詳細説明"},
                "priority": {"type": "string", "enum": ["low", "normal", "high"], "description": "優先度"},
                "session_id": {"type": "string", "description": "関連する会話セッションのID"},
                "due_date": {"type": "string", "description": "期限（YYYY-MM-DD形式）"},
                "scope": {
                    "type": "string",
                    "enum": ["session", "global"],
                    "description": "スコープ。既定は global。session は TodoWrite 連携専用で通常使わない",
                },
                "source": {
                    "type": "string",
                    "enum": ["manual", "todowrite", "mcp"],
                    "description": "出どころ。既定は manual",
                },
            },
            "required": ["title"],
        },
    },
    "task_list": {
        "description": "タスク一覧を取得する。status/scope/source でフィルタ可。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["todo", "in_progress", "done", "cancelled"],
                    "description": "ステータスでフィルタ",
                },
                "session_id": {"type": "string", "description": "セッションIDでフィルタ"},
                "scope": {
                    "type": "string",
                    "enum": ["session", "global"],
                    "description": "スコープでフィルタ",
                },
                "source": {
                    "type": "string",
                    "enum": ["manual", "todowrite", "mcp"],
                    "description": "出どころでフィルタ",
                },
            },
        },
    },
    "task_update": {
        "description": "タスクを更新する。ステータス変更（todo→in_progress→done）や内容修正に使う。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "タスクID（必須）"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": ["todo", "in_progress", "done", "cancelled"]},
                "priority": {"type": "string", "enum": ["low", "normal", "high"]},
                "due_date": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    "task_add_note": {
        "description": "タスクに作業メモ・進捗メモを追加する。途中経過や判断理由を残したい時に使う。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "タスクID（必須）"},
                "note": {"type": "string", "description": "メモ内容（必須）"},
            },
            "required": ["task_id", "note"],
        },
    },
    "task_delete": {
        "description": "タスクを削除する。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "タスクID（必須）"},
            },
            "required": ["task_id"],
        },
    },
    "task_resume_context": {
        "description": "未完了タスクとそのメモを一覧で返す。会話が途切れた後の再開時、「前回どこまでやったか」を確認したい時に使う。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
}

TOOL_HANDLERS = {
    "task_create": tool_task_create,
    "task_list": tool_task_list,
    "task_update": tool_task_update,
    "task_add_note": tool_task_add_note,
    "task_delete": tool_task_delete,
    "task_resume_context": tool_task_resume_context,
}


def _send(obj: dict):
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _handle(msg: dict):
    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        _send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "kblite-tasks", "version": "1.0.0"},
                },
            }
        )

    elif method == "notifications/initialized":
        pass  # 通知なのでレスポンス不要

    elif method == "tools/list":
        tools_list = [
            {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
            for name, spec in TOOLS.items()
        ]
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools_list}})

    elif method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }
            )
            return
        try:
            result_text = handler(args)
        except Exception as e:
            result_text = json.dumps({"error": str(e)}, ensure_ascii=False)
        _send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
            }
        )

    else:
        if msg_id is not None:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle(msg)


if __name__ == "__main__":
    main()
