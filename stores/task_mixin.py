"""タスク管理 Mixin — tasks / task_notes テーブルの CRUD"""

import uuid
from datetime import datetime

from stores._base import StoreMixinBase


class TaskMixin(StoreMixinBase):
    """tasks と task_notes テーブルを操作する Mixin"""

    # ── スキーマ定義 ────────────────────────────────────────
    # source: 'manual' | 'todowrite' | 'mcp' — タスクの出どころ
    # scope : 'session' | 'global'            — 有効スコープ（セッション限定/横断）
    # todo_key: TodoWrite同期用の一意キー ({session_id}:{todo_id})

    TASK_DDL = """
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
    """

    # ── 初期化（SQLiteStore._init_db() から呼ばれる想定） ──

    def _init_tasks(self):
        self._conn.executescript(self.TASK_DDL)
        self._migrate_tasks_columns()
        self._conn.commit()

    def _migrate_tasks_columns(self):
        """既存tasksテーブルに source/scope/todo_key が無い場合に追加する。"""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "source" not in cols:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN source TEXT DEFAULT 'manual'")
        if "scope" not in cols:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN scope TEXT DEFAULT 'global'")
        if "todo_key" not in cols:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN todo_key TEXT DEFAULT NULL")
        # 追加後にインデックスを張る（既にあれば IF NOT EXISTS でスキップ）
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_todo_key "
            "ON tasks(todo_key) WHERE todo_key IS NOT NULL"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_scope_status ON tasks(scope, status)")

    # ── タスク CRUD ─────────────────────────────────────────

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: str = "normal",
        session_id: str | None = None,
        due_date: str | None = None,
        source: str = "manual",
        scope: str = "global",
        todo_key: str | None = None,
    ) -> dict:
        task_id = str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO tasks (id, title, description, priority, session_id, due_date,
                                  source, scope, todo_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, title, description, priority, session_id, due_date, source, scope, todo_key),
        )
        self._conn.commit()
        result = self.get_task(task_id)
        assert result is not None
        return result

    def upsert_todowrite_task(
        self, todo_key: str, title: str, status: str, session_id: str | None = None
    ) -> dict:
        """TodoWrite由来のタスクを todo_key をキーに UPSERT する。

        既存があれば title/status/session_id/updated_at を更新、
        無ければ scope='session', source='todowrite' で新規作成する。
        """
        row = self._conn.execute("SELECT * FROM tasks WHERE todo_key = ?", (todo_key,)).fetchone()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        norm_status = self._normalize_todowrite_status(status)

        if row is None:
            task_id = str(uuid.uuid4())
            completed_at = now if norm_status == "done" else None
            self._conn.execute(
                """INSERT INTO tasks (id, title, description, status, priority,
                                      session_id, source, scope, todo_key,
                                      created_at, updated_at, completed_at)
                   VALUES (?, ?, '', ?, 'normal', ?, 'todowrite', 'session', ?,
                           ?, ?, ?)""",
                (task_id, title, norm_status, session_id, todo_key, now, now, completed_at),
            )
            self._conn.commit()
            result = self.get_task(task_id)
            assert result is not None
            return result

        # 既存レコード更新
        prev_status = row["status"]
        completed_at = row["completed_at"]
        if norm_status == "done" and prev_status != "done":
            completed_at = now
        elif norm_status != "done":
            completed_at = None

        self._conn.execute(
            """UPDATE tasks
                  SET title = ?, status = ?, session_id = COALESCE(?, session_id),
                      updated_at = ?, completed_at = ?
                WHERE todo_key = ?""",
            (title, norm_status, session_id, now, completed_at, todo_key),
        )
        self._conn.commit()
        result = self.get_task(row["id"])
        assert result is not None
        return result

    @staticmethod
    def _normalize_todowrite_status(status: str) -> str:
        """TodoWriteのステータス（pending/in_progress/completed）を tasks.status に正規化。"""
        mapping = {
            "pending": "todo",
            "in_progress": "in_progress",
            "completed": "done",
        }
        return mapping.get((status or "").strip(), "todo")

    def get_task(self, task_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return self._task_to_dict(row)

    def list_tasks(
        self,
        status: str | None = None,
        session_id: str | None = None,
        scope: str | None = None,
        source: str | None = None,
    ) -> list[dict]:
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
        sql += " ORDER BY CASE status WHEN 'in_progress' THEN 0 WHEN 'todo' THEN 1 WHEN 'done' THEN 2 ELSE 3 END, updated_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        result = []
        for row in rows:
            task = self._task_to_dict(row)
            task["notes"] = self._list_notes_for(task["id"])
            result.append(task)
        return result

    def update_task(self, task_id: str, **kwargs) -> dict | None:
        allowed = {
            "title",
            "description",
            "status",
            "priority",
            "session_id",
            "due_date",
            "source",
            "scope",
            "todo_key",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_task(task_id)

        # done に変更した場合は completed_at を記録
        if updates.get("status") == "done":
            updates["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif "status" in updates and updates["status"] != "done":
            updates["completed_at"] = None

        updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        self._conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        self._conn.commit()
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # ── ノート CRUD ─────────────────────────────────────────

    def add_task_note(self, task_id: str, note: str) -> dict:
        note_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO task_notes (id, task_id, note) VALUES (?, ?, ?)",
            (note_id, task_id, note),
        )
        # タスクの updated_at を更新
        self._conn.execute(
            "UPDATE tasks SET updated_at = datetime('now','localtime') WHERE id = ?",
            (task_id,),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT * FROM task_notes WHERE id = ?", (note_id,)).fetchone()
        return dict(row)

    def _list_notes_for(self, task_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM task_notes WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── ヘルパー ────────────────────────────────────────────

    @staticmethod
    def _task_to_dict(row) -> dict:
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
