"""KBLite Browser UI ルートテスト"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastapi.testclient import TestClient
from app import app, get_db
from db import KBLiteDB


@pytest.fixture
def db():
    """インメモリDBでテスト用"""
    database = KBLiteDB(":memory:")
    yield database
    database.close()


@pytest.fixture
def client(db):
    """テスト用FastAPIクライアント（DBをインメモリに差し替え）"""
    app.dependency_overrides[get_db] = lambda: db

    def _override_get_db():
        return db

    # get_db関数をモンキーパッチ
    import app as app_module
    original = app_module.get_db
    app_module.get_db = _override_get_db

    with TestClient(app) as c:
        yield c

    app_module.get_db = original
    app.dependency_overrides.clear()


class TestIndex:
    """GET / テスト"""

    def test_status_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_contains_dashboard(self, client):
        resp = client.get("/")
        assert "Dashboard" in resp.text

    def test_stats_displayed(self, client, db):
        db.save_conversation("s1", "user", "Hello", 1, title="Test")
        resp = client.get("/")
        assert "Sessions" in resp.text


class TestSessions:
    """GET /sessions テスト"""

    def test_status_200(self, client):
        resp = client.get("/sessions")
        assert resp.status_code == 200

    def test_pagination_params(self, client):
        resp = client.get("/sessions?limit=5&offset=0")
        assert resp.status_code == 200

    def test_lists_sessions(self, client, db):
        db.save_conversation("s1", "user", "Hi", 1, title="Session One")
        resp = client.get("/sessions")
        assert "Session One" in resp.text


class TestSessionDetail:
    """GET /session/{id} テスト"""

    def test_existing_session(self, client, db):
        db.save_conversation("s1", "user", "Hello World", 1, title="My Session")
        resp = client.get("/session/s1")
        assert resp.status_code == 200
        assert "My Session" in resp.text

    def test_nonexistent_session(self, client):
        resp = client.get("/session/nonexistent")
        assert resp.status_code == 404


class TestSearch:
    """GET /search テスト"""

    def test_empty_search(self, client):
        resp = client.get("/search")
        assert resp.status_code == 200

    def test_search_with_query(self, client, db):
        db.save_conversation("s1", "user", "Python programming", 1, title="Python")
        resp = client.get("/search?q=Python")
        assert resp.status_code == 200
        assert "Python" in resp.text


class TestMemories:
    """GET /memories テスト"""

    def test_status_200(self, client):
        resp = client.get("/memories")
        assert resp.status_code == 200

    def test_with_filter(self, client, db):
        db.save_memory("Test Memo", "Content here", "general", tags=["test"])
        resp = client.get("/memories?category=general")
        assert resp.status_code == 200


class TestMemoryDetail:
    """GET /memory/{id} テスト"""

    def test_existing_memory(self, client, db):
        result = db.save_memory("My Memo", "Memo content", "general")
        resp = client.get(f"/memory/{result['memory_id']}")
        assert resp.status_code == 200
        assert "My Memo" in resp.text

    def test_nonexistent_memory(self, client):
        resp = client.get("/memory/99999")
        assert resp.status_code == 200  # テンプレートは表示される
