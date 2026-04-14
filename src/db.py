"""KBLite DAO層 - SQLite + FTS5 によるデータアクセス"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone


class KBLiteDB:
    """SQLite + FTS5 を用いた会話・メモの永続化クラス"""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = os.environ.get(
                "KBLITE_DB_PATH",
                os.path.join(os.path.dirname(__file__), "..", "data", "kblite.db"),
            )
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cur = self._conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")

        cur.executescript(
            """
            -- sessions
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                message_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC);

            -- conversations
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                turn_number INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id, turn_number);

            -- memories
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general'
                    CHECK(category IN ('user', 'project', 'reference', 'feedback', 'general')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at DESC);

            -- memory_tags
            CREATE TABLE IF NOT EXISTS memory_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                tag TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tags_memory ON memory_tags(memory_id);
            CREATE INDEX IF NOT EXISTS idx_tags_tag ON memory_tags(tag);

            -- FTS5: conversations
            CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
                content,
                content='conversations',
                content_rowid='id',
                tokenize='unicode61'
            );

            -- FTS5: memories
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                title,
                content,
                content='memories',
                content_rowid='id',
                tokenize='unicode61'
            );

            -- FTS5 triggers: conversations
            CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
                INSERT INTO conversations_fts(rowid, content) VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
                INSERT INTO conversations_fts(conversations_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
                INSERT INTO conversations_fts(conversations_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
                INSERT INTO conversations_fts(rowid, content) VALUES (new.id, new.content);
            END;

            -- FTS5 triggers: memories
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, title, content)
                    VALUES (new.id, new.title, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, title, content)
                    VALUES('delete', old.id, old.title, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, title, content)
                    VALUES('delete', old.id, old.title, old.content);
                INSERT INTO memories_fts(rowid, title, content)
                    VALUES (new.id, new.title, new.content);
            END;
            """
        )
        self._conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def save_conversation(
        self,
        session_id: str,
        role: str,
        content: str,
        turn_number: int,
        title: str | None = None,
    ) -> dict:
        """会話を保存する。セッションが存在しなければ自動作成する。"""
        cur = self._conn.cursor()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # セッション存在チェック・自動作成
        row = cur.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            session_title = title or f"Session {session_id[:8]}"
            cur.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at, message_count) VALUES (?, ?, ?, ?, 0)",
                (session_id, session_title, now, now),
            )

        # 会話INSERT
        cur.execute(
            "INSERT INTO conversations (session_id, role, content, created_at, turn_number) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, now, turn_number),
        )
        conversation_id = cur.lastrowid

        # message_count・updated_at 更新
        cur.execute(
            "UPDATE sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
            (now, session_id),
        )

        # titleが指定されていて既存セッションの場合も更新
        if title and row is not None:
            cur.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))

        self._conn.commit()
        return {"conversation_id": conversation_id, "session_id": session_id}

    def search_conversations(
        self, query: str, limit: int = 20, session_id: str | None = None
    ) -> dict:
        """FTS5で会話を検索する。"""
        cur = self._conn.cursor()

        if session_id:
            rows = cur.execute(
                """
                SELECT c.id, c.session_id, s.title AS session_title, c.role, c.content,
                       highlight(conversations_fts, 0, '<mark>', '</mark>') AS highlighted,
                       c.created_at, c.turn_number
                FROM conversations_fts
                JOIN conversations c ON c.id = conversations_fts.rowid
                JOIN sessions s ON s.id = c.session_id
                WHERE conversations_fts MATCH ? AND c.session_id = ?
                ORDER BY bm25(conversations_fts)
                LIMIT ?
                """,
                (query, session_id, limit),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT c.id, c.session_id, s.title AS session_title, c.role, c.content,
                       highlight(conversations_fts, 0, '<mark>', '</mark>') AS highlighted,
                       c.created_at, c.turn_number
                FROM conversations_fts
                JOIN conversations c ON c.id = conversations_fts.rowid
                JOIN sessions s ON s.id = c.session_id
                WHERE conversations_fts MATCH ?
                ORDER BY bm25(conversations_fts)
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()

        return {"results": [dict(r) for r in rows]}

    def save_memory(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: list[str] | None = None,
    ) -> dict:
        """メモを保存する。"""
        cur = self._conn.cursor()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        cur.execute(
            "INSERT INTO memories (title, content, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (title, content, category, now, now),
        )
        memory_id = cur.lastrowid

        if tags:
            cur.executemany(
                "INSERT INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                [(memory_id, tag) for tag in tags],
            )

        self._conn.commit()
        return {"memory_id": memory_id}

    def search_memories(
        self, query: str, category: str | None = None, limit: int = 20
    ) -> dict:
        """FTS5でメモを検索する。"""
        cur = self._conn.cursor()

        if category:
            rows = cur.execute(
                """
                SELECT m.id, m.title, m.content, m.category,
                       highlight(memories_fts, 0, '<mark>', '</mark>') AS highlighted_title,
                       highlight(memories_fts, 1, '<mark>', '</mark>') AS highlighted_content,
                       m.created_at, m.updated_at
                FROM memories_fts
                JOIN memories m ON m.id = memories_fts.rowid
                WHERE memories_fts MATCH ? AND m.category = ?
                ORDER BY bm25(memories_fts)
                LIMIT ?
                """,
                (query, category, limit),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT m.id, m.title, m.content, m.category,
                       highlight(memories_fts, 0, '<mark>', '</mark>') AS highlighted_title,
                       highlight(memories_fts, 1, '<mark>', '</mark>') AS highlighted_content,
                       m.created_at, m.updated_at
                FROM memories_fts
                JOIN memories m ON m.id = memories_fts.rowid
                WHERE memories_fts MATCH ?
                ORDER BY bm25(memories_fts)
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            # タグ取得
            tags = cur.execute(
                "SELECT tag FROM memory_tags WHERE memory_id = ?", (d["id"],)
            ).fetchall()
            d["tags"] = [t["tag"] for t in tags]
            results.append(d)

        return {"results": results}

    def list_sessions(self, limit: int = 50, offset: int = 0) -> dict:
        """セッション一覧を返す。"""
        cur = self._conn.cursor()

        total = cur.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

        rows = cur.execute(
            """
            SELECT id, title, created_at, updated_at, message_count
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

        return {"sessions": [dict(r) for r in rows], "total": total}
