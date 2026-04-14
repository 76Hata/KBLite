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
        self._init_db()
        logger.info("SQLiteStore 初期化完了: %s", db_path)

    def _init_db(self):
        """テーブルの初期化"""
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
                first_message TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT (datetime('now')),
                updated_at DATETIME DEFAULT (datetime('now')),
                model TEXT DEFAULT NULL,
                title TEXT DEFAULT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT (datetime('now')),
                updated_at DATETIME DEFAULT (datetime('now'))
            );
        """)
        self._conn.commit()

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
