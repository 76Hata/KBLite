"""KBLite SQLite ストア — session/conversation/project のみ管理"""
import logging
import sqlite3
from pathlib import Path

from stores import SessionMixin, ConversationMixin, ProjectMixin

logger = logging.getLogger(__name__)


class SQLiteStore(SessionMixin, ConversationMixin, ProjectMixin):
    """SQLiteを使った構造化データストア（KBLite軽量版）"""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            import os
            db_path = os.getenv("SQLITE_PATH", str(Path(__file__).parent / "data" / "sqlite" / "kblite.db"))
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self._migrate_db()
        logger.info("SQLiteStore 初期化完了: %s", db_path)

    def _init_db(self):
        """テーブルの初期化（新規DB用）"""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at DATETIME DEFAULT (datetime('now')),
                updated_at DATETIME DEFAULT (datetime('now')),
                category TEXT DEFAULT '',
                bookmarked INTEGER DEFAULT 0,
                parent_session_id TEXT DEFAULT NULL,
                project_id TEXT DEFAULT NULL,
                message_count INTEGER DEFAULT 0,
                first_message TEXT DEFAULT '',
                fork_number INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                sequence INTEGER NOT NULL DEFAULT 0,
                question TEXT NOT NULL DEFAULT '',
                answer TEXT NOT NULL DEFAULT '',
                title TEXT DEFAULT NULL,
                summary TEXT DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT (datetime('now')),
                updated_at DATETIME DEFAULT (datetime('now')),
                session_count INTEGER DEFAULT 0
            );
        """)
        self._conn.commit()

    def _migrate_db(self):
        """既存DBに不足カラムを追加するマイグレーション"""
        # sessions: fork_number
        existing_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(sessions)")}
        if "fork_number" not in existing_cols:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN fork_number INTEGER DEFAULT 0")
            logger.info("Migration: sessions.fork_number カラムを追加")
            self._conn.commit()

        # projects: session_count
        proj_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(projects)")}
        if "session_count" not in proj_cols:
            self._conn.execute("ALTER TABLE projects ADD COLUMN session_count INTEGER DEFAULT 0")
            logger.info("Migration: projects.session_count カラムを追加")
            self._conn.commit()

        # conversations: 旧スキーマ(role/content)から新スキーマ(question/answer/sequence)へ移行
        conv_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(conversations)")}
        if "role" in conv_cols and "question" not in conv_cols:
            # 旧テーブルを退避してから新スキーマで再作成（旧データは捨てる）
            logger.info("Migration: conversations テーブルを新スキーマへ再作成")
            self._conn.execute("DROP TABLE IF EXISTS conversations_old")
            self._conn.execute("ALTER TABLE conversations RENAME TO conversations_old")
            self._conn.execute("""
                CREATE TABLE conversations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    question TEXT NOT NULL DEFAULT '',
                    answer TEXT NOT NULL DEFAULT '',
                    title TEXT DEFAULT NULL,
                    summary TEXT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            self._conn.execute("DROP TABLE IF EXISTS conversations_old")
            self._conn.commit()
            return

        # 既に新スキーマだが不足カラムがある場合は追加
        missing = []
        if "sequence" not in conv_cols:
            missing.append("ALTER TABLE conversations ADD COLUMN sequence INTEGER NOT NULL DEFAULT 0")
        if "question" not in conv_cols:
            missing.append("ALTER TABLE conversations ADD COLUMN question TEXT NOT NULL DEFAULT ''")
        if "answer" not in conv_cols:
            missing.append("ALTER TABLE conversations ADD COLUMN answer TEXT NOT NULL DEFAULT ''")
        if "summary" not in conv_cols:
            missing.append("ALTER TABLE conversations ADD COLUMN summary TEXT DEFAULT NULL")
        for sql in missing:
            self._conn.execute(sql)
            logger.info("Migration: %s", sql)
        if missing:
            self._conn.commit()

    def _session_to_dict(self, row) -> dict:
        """sqlite3.Row を dict に変換"""
        return {
            "id": row["id"],
            "session_id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "category": row["category"] or "",
            "bookmarked": bool(row["bookmarked"]),
            "parent_session_id": row["parent_session_id"] or "",
            "project_id": row["project_id"] or "",
            "message_count": row["message_count"] or 0,
            "first_message": row["first_message"] or "",
            "fork_number": row["fork_number"] if "fork_number" in row.keys() else 0,
        }

    def _project_to_dict(self, row) -> dict:
        """sqlite3.Row を dict に変換（projects テーブル用）"""
        return {
            "project_id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "session_count": row["session_count"] if "session_count" in row.keys() else 0,
        }

    def sqlite_healthcheck(self) -> bool:
        """SQLite 疎通確認"""
        try:
            self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def close(self):
        """接続を閉じる"""
        if self._conn:
            self._conn.close()

    def __del__(self):
        self.close()
