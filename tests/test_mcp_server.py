"""MCP Server ツール定義テスト（DB連携の統合テスト）"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import KBLiteDB

# MCP Server のツール関数を直接テストするため、DBを差し替える
import mcp_server


@pytest.fixture(autouse=True)
def setup_db():
    """各テストでインメモリDBに差し替える"""
    mcp_server._db = KBLiteDB(":memory:")
    yield
    mcp_server._db.close()
    mcp_server._db = None


class TestSaveConversationTool:
    def test_basic(self):
        result = mcp_server.save_conversation("s1", "user", "Hello world", 1, "Test")
        assert "conversation_id" in result
        assert result["session_id"] == "s1"

    def test_without_title(self):
        result = mcp_server.save_conversation("s2", "assistant", "Hi there", 1)
        assert result["session_id"] == "s2"


class TestSearchConversationsTool:
    def test_search(self):
        mcp_server.save_conversation("s1", "user", "Python programming", 1, "Python Session")
        result = mcp_server.search_conversations("Python")
        assert len(result["results"]) >= 1

    def test_empty_result(self):
        result = mcp_server.search_conversations("nonexistent_keyword_xyz")
        assert result["results"] == []


class TestSaveMemoryTool:
    def test_basic(self):
        result = mcp_server.save_memory("Memo Title", "Memo content")
        assert "memory_id" in result

    def test_with_category_and_tags(self):
        result = mcp_server.save_memory("Ref", "Data", "reference", ["tag1"])
        assert result["memory_id"] is not None


class TestSearchMemoriesTool:
    def test_search(self):
        mcp_server.save_memory("Python Tips", "Use generators for efficiency")
        result = mcp_server.search_memories("Python")
        assert len(result["results"]) >= 1


class TestListSessionsTool:
    def test_empty(self):
        result = mcp_server.list_sessions()
        assert result["total"] == 0

    def test_with_data(self):
        mcp_server.save_conversation("s1", "user", "Msg", 1, "Session 1")
        result = mcp_server.list_sessions()
        assert result["total"] == 1
