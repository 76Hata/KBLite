"""タスク管理 Mixin — tasks / task_notes テーブルの CRUD"""
import uuid
from datetime import datetime


class TaskMixin:
    """tasks と task_notes テーブルを操作する Mixin"""

    # ── スキーマ定義 ────────────────────────────────────────

    TASK_DDL = """
        CREATE TABLE IF NOT EXISTS tasks (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            description TEXT DEFAULT '',
            status      TEXT DEFAULT 'todo',
            priority    TEXT DEFAULT 'normal',
            session_id  TEXT DEFAULT NULL,
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
        self._conn.commit()

    # ── タスク CRUD ─────────────────────────────────────────

    def create_task(self, title: str, description: str = "",
                    priority: str = "normal", session_id: str | None = None,
                    due_date: str | None = None) -> dict:
        task_id = str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO tasks (id, title, description, priority, session_id, due_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, title, description, priority, session_id, due_date),
        )
        self._conn.commit()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return self._task_to_dict(row)

    def list_tasks(self, status: str | None = None,
                   session_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM tasks WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        sql += " ORDER BY CASE status WHEN 'in_progress' THEN 0 WHEN 'todo' THEN 1 WHEN 'done' THEN 2 ELSE 3 END, updated_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        result = []
        for row in rows:
            task = self._task_to_dict(row)
            task["notes"] = self._list_notes_for(task["id"])
            result.append(task)
        return result

    def update_task(self, task_id: str, **kwargs) -> dict | None:
        allowed = {"title", "description", "status", "priority",
                   "session_id", "due_date"}
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
        self._conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?", values
        )
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
        row = self._conn.execute(
            "SELECT * FROM task_notes WHERE id = ?", (note_id,)
        ).fetchone()
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
        return {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"] or "",
            "status": row["status"],
            "priority": row["priority"],
            "session_id": row["session_id"] or None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "due_date": row["due_date"] or None,
            "completed_at": row["completed_at"] or None,
        }
