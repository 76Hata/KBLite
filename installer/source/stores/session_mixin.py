"""セッション操作 Mixin"""

import logging
from datetime import UTC, datetime
from typing import Any

from stores._base import StoreMixinBase

logger = logging.getLogger(__name__)


class SessionMixin(StoreMixinBase):
    """sessions テーブルに対する CRUD 操作"""

    def create_session(
        self,
        session_id: str,
        title: str,
        first_message: str,
        category: str = "",
        project_id: str = "",
        parent_session_id: str = "",
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        fork_number = 0
        if parent_session_id:
            cursor = self._conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE parent_session_id = ?",
                (parent_session_id,),
            )
            fork_number = (cursor.fetchone()[0] or 0) + 1
        self._conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, title, created_at, updated_at, message_count,
                first_message, category, project_id, parent_session_id, fork_number)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                title,
                now,
                now,
                1,
                first_message[:100],
                category,
                project_id,
                parent_session_id,
                fork_number,
            ),
        )
        self._conn.commit()
        logger.info(
            "Created session '%s': %s (parent=%s, fork#%d)",
            session_id,
            title,
            parent_session_id or "-",
            fork_number,
        )
        return {
            "session_id": session_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "message_count": 1,
            "first_message": first_message[:100],
            "category": category,
            "project_id": project_id,
            "parent_session_id": parent_session_id,
            "fork_number": fork_number,
        }

    def update_session(
        self,
        session_id: str,
        title: str | None = None,
        message_count: int | None = None,
        project_id: str | None = None,
        bookmarked: bool | None = None,
        touch_updated_at: bool = True,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        if touch_updated_at:
            updates.append("updated_at = ?")
            params.append(datetime.now(UTC).isoformat())
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if message_count is not None:
            updates.append("message_count = ?")
            params.append(message_count)
        if project_id is not None:
            updates.append("project_id = ?")
            params.append(project_id)
        if bookmarked is not None:
            updates.append("bookmarked = ?")
            params.append(1 if bookmarked else 0)
        if not updates:
            return
        params.append(session_id)
        sql = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"
        self._conn.execute(sql, params)
        self._conn.commit()

    def list_sessions(
        self,
        project_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        if project_id == "__unassigned__":
            conditions.append("(project_id IS NULL OR project_id = '')")
        elif project_id == "__bookmarked__":
            conditions.append("COALESCE(bookmarked, 0) = 1")
        elif project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params += [limit, offset]
        cursor = self._conn.execute(
            f"SELECT * FROM sessions {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params,
        )
        return [self._session_to_dict(row) for row in cursor.fetchall()]

    def count_sessions(self, project_id: str | None = None) -> int:
        conditions: list[str] = []
        params: list = []
        if project_id == "__unassigned__":
            conditions.append("(project_id IS NULL OR project_id = '')")
        elif project_id == "__bookmarked__":
            conditions.append("COALESCE(bookmarked, 0) = 1")
        elif project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor = self._conn.execute(f"SELECT COUNT(*) FROM sessions {where}", params)
        return cursor.fetchone()[0]

    def get_session(self, session_id: str) -> dict | None:
        cursor = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._session_to_dict(row)

    def delete_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()
        logger.info("Deleted session '%s' and its conversations", session_id)

    def get_session_ids_by_project(self, project_id: str) -> list[str]:
        cursor = self._conn.execute("SELECT id FROM sessions WHERE project_id = ?", (project_id,))
        return [row["id"] for row in cursor.fetchall()]
