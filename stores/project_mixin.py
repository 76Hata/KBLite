"""プロジェクト操作 Mixin"""

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class ProjectMixin:
    """projects テーブルに対する CRUD 操作"""

    def create_project(self, project_id: str, name: str) -> dict:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO projects
               (id, name, created_at, updated_at, session_count)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, name, now, now, 0),
        )
        self._conn.commit()
        logger.info("Created project '%s': %s", project_id, name)
        return {
            "project_id": project_id,
            "name": name,
            "created_at": now,
            "updated_at": now,
            "session_count": 0,
        }

    def list_projects(self) -> list[dict]:
        cursor = self._conn.execute("SELECT * FROM projects ORDER BY name")
        return [self._project_to_dict(row) for row in cursor.fetchall()]

    def delete_project(self, project_id: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET project_id = '' WHERE project_id = ?",
            (project_id,),
        )
        self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._conn.commit()
        logger.info("Deleted project '%s'", project_id)

    def rename_project(self, project_id: str, name: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
            (name, now, project_id),
        )
        self._conn.commit()

    def move_session_to_project(self, session_id: str, project_id: str) -> None:
        self.update_session(session_id, project_id=project_id, touch_updated_at=False)
