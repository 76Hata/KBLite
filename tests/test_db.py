"""KBLiteDB ユニットテスト"""

import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import KBLiteDB


@pytest.fixture
def db():
    """インメモリDBでテスト用KBLiteDBを生成"""
    database = KBLiteDB(":memory:")
    yield database
    database.close()


class TestDBInit:
    """DB初期化テスト"""

    def test_tables_created(self, db):
        """テーブルが正しく作成されていること"""
        cur = db._conn.cursor()
        tables = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "sessions" in table_names
        assert "conversations" in table_names
        assert "memories" in table_names
        assert "memory_tags" in table_names

    def test_fts5_tables_created(self, db):
        """FTS5仮想テーブルが作成されていること"""
        cur = db._conn.cursor()
        tables = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "conversations_fts" in table_names
        assert "memories_fts" in table_names

    def test_triggers_created(self, db):
        """同期トリガーが作成されていること"""
        cur = db._conn.cursor()
        triggers = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
        ).fetchall()
        trigger_names = [t["name"] for t in triggers]
        expected = [
            "conversations_ai", "conversations_ad", "conversations_au",
            "memories_ai", "memories_ad", "memories_au",
        ]
        for name in expected:
            assert name in trigger_names

    def test_wal_mode(self, db):
        """WALモードが有効であること（in-memoryはmemoryになるため条件分岐）"""
        cur = db._conn.cursor()
        mode = cur.execute("PRAGMA journal_mode").fetchone()[0]
        # in-memory DBではWALにならない場合があるので存在確認のみ
        assert mode in ("wal", "memory")


class TestSaveConversation:
    """save_conversation テスト"""

    def test_new_session_created(self, db):
        """新規セッションが自動作成されること"""
        result = db.save_conversation("sess-001", "user", "Hello", 1, title="Test Session")
        assert result["session_id"] == "sess-001"
        assert result["conversation_id"] is not None

        sessions = db.list_sessions()
        assert sessions["total"] == 1
        assert sessions["sessions"][0]["title"] == "Test Session"

    def test_default_title(self, db):
        """titleを省略するとデフォルトタイトルが付くこと"""
        db.save_conversation("sess-002", "user", "Hi", 1)
        sessions = db.list_sessions()
        assert sessions["sessions"][0]["title"] == "Session sess-002"

    def test_conversation_added(self, db):
        """会話がINSERTされること"""
        db.save_conversation("sess-001", "user", "Question", 1, title="Test")
        db.save_conversation("sess-001", "assistant", "Answer", 1)

        cur = db._conn.cursor()
        rows = cur.execute(
            "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY id",
            ("sess-001",),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["role"] == "user"
        assert rows[1]["role"] == "assistant"

    def test_message_count_updated(self, db):
        """message_countがインクリメントされること"""
        db.save_conversation("sess-001", "user", "Q1", 1, title="Test")
        db.save_conversation("sess-001", "assistant", "A1", 1)
        db.save_conversation("sess-001", "user", "Q2", 2)

        sessions = db.list_sessions()
        assert sessions["sessions"][0]["message_count"] == 3

    def test_title_update_on_existing_session(self, db):
        """既存セッションのtitleを上書きできること"""
        db.save_conversation("sess-001", "user", "Hi", 1, title="Old Title")
        db.save_conversation("sess-001", "assistant", "Hello", 1, title="New Title")

        sessions = db.list_sessions()
        assert sessions["sessions"][0]["title"] == "New Title"


class TestSearchConversations:
    """search_conversations テスト"""

    def test_fts5_search(self, db):
        """FTS5でキーワード検索できること"""
        db.save_conversation("s1", "user", "Python programming tutorial", 1, title="Python")
        db.save_conversation("s1", "assistant", "Here is a Python example", 1)
        db.save_conversation("s2", "user", "JavaScript basics", 1, title="JS")

        result = db.search_conversations("Python")
        assert len(result["results"]) == 2

    def test_session_id_filter(self, db):
        """session_idで絞り込みできること"""
        db.save_conversation("s1", "user", "Python guide", 1, title="S1")
        db.save_conversation("s2", "user", "Python tips", 1, title="S2")

        result = db.search_conversations("Python", session_id="s1")
        assert len(result["results"]) == 1
        assert result["results"][0]["session_id"] == "s1"

    def test_highlighted_result(self, db):
        """highlightが含まれること"""
        db.save_conversation("s1", "user", "Learn Python today", 1, title="Test")
        result = db.search_conversations("Python")
        assert "<mark>" in result["results"][0]["highlighted"]

    def test_limit(self, db):
        """limit制限が効くこと"""
        for i in range(5):
            db.save_conversation(f"s{i}", "user", f"Python topic {i}", 1, title=f"S{i}")

        result = db.search_conversations("Python", limit=3)
        assert len(result["results"]) == 3


class TestSaveMemory:
    """save_memory テスト"""

    def test_basic_save(self, db):
        """メモが保存されること"""
        result = db.save_memory("Test Memo", "This is content", "general")
        assert result["memory_id"] is not None

    def test_with_tags(self, db):
        """タグ付きメモが保存されること"""
        result = db.save_memory("Tagged", "Content", "user", tags=["python", "tips"])

        cur = db._conn.cursor()
        tags = cur.execute(
            "SELECT tag FROM memory_tags WHERE memory_id = ? ORDER BY tag",
            (result["memory_id"],),
        ).fetchall()
        assert [t["tag"] for t in tags] == ["python", "tips"]

    def test_category_stored(self, db):
        """カテゴリが正しく保存されること"""
        db.save_memory("Ref", "Data", "reference")
        cur = db._conn.cursor()
        row = cur.execute("SELECT category FROM memories WHERE title = 'Ref'").fetchone()
        assert row["category"] == "reference"


class TestSearchMemories:
    """search_memories テスト"""

    def test_fts5_search(self, db):
        """FTS5でメモ検索できること"""
        db.save_memory("Python Tips", "Use list comprehensions", "general")
        db.save_memory("Git Guide", "Git branch workflow", "reference")

        result = db.search_memories("Python")
        assert len(result["results"]) >= 1

    def test_category_filter(self, db):
        """カテゴリフィルタが効くこと"""
        db.save_memory("Python Memo", "Content A", "user")
        db.save_memory("Python Ref", "Content B", "reference")

        result = db.search_memories("Python", category="reference")
        assert len(result["results"]) == 1
        assert result["results"][0]["category"] == "reference"

    def test_tags_included(self, db):
        """検索結果にタグが含まれること"""
        db.save_memory("Tagged Memo", "Content with tags", "general", tags=["tag1", "tag2"])

        result = db.search_memories("tags")
        assert len(result["results"]) >= 1
        assert "tag1" in result["results"][0]["tags"]

    def test_highlighted_fields(self, db):
        """highlight結果が含まれること"""
        db.save_memory("Python Guide", "Learn Python basics", "general")

        result = db.search_memories("Python")
        r = result["results"][0]
        assert "highlighted_title" in r
        assert "highlighted_content" in r


class TestListSessions:
    """list_sessions テスト"""

    def test_empty(self, db):
        """セッションがない場合"""
        result = db.list_sessions()
        assert result["total"] == 0
        assert result["sessions"] == []

    def test_pagination(self, db):
        """ページネーションが機能すること"""
        for i in range(10):
            db.save_conversation(f"s{i:03d}", "user", f"Msg {i}", 1, title=f"Session {i}")

        page1 = db.list_sessions(limit=3, offset=0)
        page2 = db.list_sessions(limit=3, offset=3)

        assert page1["total"] == 10
        assert len(page1["sessions"]) == 3
        assert len(page2["sessions"]) == 3
        # 重複しないこと
        ids1 = {s["id"] for s in page1["sessions"]}
        ids2 = {s["id"] for s in page2["sessions"]}
        assert ids1.isdisjoint(ids2)

    def test_order_by_updated(self, db):
        """updated_at降順でソートされること"""
        db.save_conversation("s1", "user", "First", 1, title="First")
        db.save_conversation("s2", "user", "Second", 1, title="Second")
        # s1に追記 → s1のupdated_atが最新になる
        db.save_conversation("s1", "user", "Third", 2)

        result = db.list_sessions()
        assert result["sessions"][0]["id"] == "s1"


class TestGetSession:
    """get_session テスト"""

    def test_existing_session(self, db):
        """存在するセッションを取得できること"""
        db.save_conversation("sess-001", "user", "Hello", 1, title="Test Session")
        result = db.get_session("sess-001")
        assert result is not None
        assert result["id"] == "sess-001"
        assert result["title"] == "Test Session"
        assert result["message_count"] == 1

    def test_nonexistent_session(self, db):
        """存在しないセッションはNoneを返すこと"""
        result = db.get_session("nonexistent")
        assert result is None


class TestGetConversationsBySession:
    """get_conversations_by_session テスト"""

    def test_returns_ordered(self, db):
        """turn_number順で会話を取得できること"""
        db.save_conversation("s1", "user", "Q1", 1, title="Test")
        db.save_conversation("s1", "assistant", "A1", 1)
        db.save_conversation("s1", "user", "Q2", 2)
        db.save_conversation("s1", "assistant", "A2", 2)

        convs = db.get_conversations_by_session("s1")
        assert len(convs) == 4
        assert convs[0]["role"] == "user"
        assert convs[0]["content"] == "Q1"
        assert convs[-1]["role"] == "assistant"
        assert convs[-1]["content"] == "A2"

    def test_empty_session(self, db):
        """会話がないセッションは空リストを返すこと"""
        convs = db.get_conversations_by_session("nonexistent")
        assert convs == []


class TestGetMemory:
    """get_memory テスト"""

    def test_existing_memory(self, db):
        """メモをタグ付きで取得できること"""
        result = db.save_memory("Test Memo", "Content", "general", tags=["tag1", "tag2"])
        memory = db.get_memory(result["memory_id"])
        assert memory is not None
        assert memory["title"] == "Test Memo"
        assert memory["content"] == "Content"
        assert memory["category"] == "general"
        assert set(memory["tags"]) == {"tag1", "tag2"}

    def test_nonexistent_memory(self, db):
        """存在しないメモはNoneを返すこと"""
        result = db.get_memory(99999)
        assert result is None


class TestGetStats:
    """get_stats テスト"""

    def test_empty_stats(self, db):
        """空のDBでは全て0を返すこと"""
        stats = db.get_stats()
        assert stats == {"sessions": 0, "conversations": 0, "memories": 0}

    def test_counts(self, db):
        """各テーブルの件数を正しくカウントすること"""
        db.save_conversation("s1", "user", "Q1", 1, title="S1")
        db.save_conversation("s1", "assistant", "A1", 1)
        db.save_conversation("s2", "user", "Q2", 1, title="S2")
        db.save_memory("Memo1", "Content1", "general")
        db.save_memory("Memo2", "Content2", "user")

        stats = db.get_stats()
        assert stats["sessions"] == 2
        assert stats["conversations"] == 3
        assert stats["memories"] == 2


class TestContextManager:
    """コンテキストマネージャテスト"""

    def test_with_statement(self):
        """with文でDBを使えること"""
        with KBLiteDB(":memory:") as db:
            db.save_conversation("s1", "user", "Test", 1, title="Test")
            result = db.list_sessions()
            assert result["total"] == 1
