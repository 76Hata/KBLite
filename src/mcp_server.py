"""KBLite MCP Server - Claude Code向け会話・メモ永続化サーバー"""

import logging
import os
import sys
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from db import KBLiteDB

# logging: stderrに出力（stdoutはJSON-RPCで使用）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("kblite")

mcp = FastMCP("kblite")

_db: KBLiteDB | None = None


def _get_db() -> KBLiteDB:
    global _db
    if _db is None:
        db_path = os.environ.get("KBLITE_DB_PATH")
        _db = KBLiteDB(db_path)
        logger.info("Database initialized: %s", _db.db_path)
    return _db


@mcp.tool()
def save_conversation(
    session_id: Annotated[str, Field(description="セッションID（UUID v4）")],
    role: Annotated[str, Field(description="発言者ロール: 'user' or 'assistant'")],
    content: Annotated[str, Field(description="会話テキスト")],
    turn_number: Annotated[int, Field(description="ターン番号（セッション内）")],
    title: Annotated[str | None, Field(description="セッションタイトル（初回のみ）")] = None,
) -> dict:
    """会話内容をセッション単位で保存する。セッションが存在しなければ自動作成する。"""
    db = _get_db()
    result = db.save_conversation(session_id, role, content, turn_number, title)
    logger.info("Saved conversation: session=%s, id=%s", session_id, result["conversation_id"])
    return result


@mcp.tool()
def search_conversations(
    query: Annotated[str, Field(description="検索キーワード")],
    limit: Annotated[int, Field(description="最大件数")] = 20,
    session_id: Annotated[str | None, Field(description="特定セッションに限定")] = None,
) -> dict:
    """保存済み会話をキーワードで全文検索する（FTS5）。"""
    db = _get_db()
    result = db.search_conversations(query, limit, session_id)
    logger.info("Search conversations: query='%s', results=%d", query, len(result["results"]))
    return result


@mcp.tool()
def save_memory(
    title: Annotated[str, Field(description="メモタイトル")],
    content: Annotated[str, Field(description="メモ内容")],
    category: Annotated[str, Field(description="カテゴリ: user/project/reference/feedback/general")] = "general",
    tags: Annotated[list[str] | None, Field(description="タグ配列")] = None,
) -> dict:
    """ユーザーメモ・学習事項を保存する。"""
    db = _get_db()
    result = db.save_memory(title, content, category, tags)
    logger.info("Saved memory: id=%s, title='%s'", result["memory_id"], title)
    return result


@mcp.tool()
def search_memories(
    query: Annotated[str, Field(description="検索キーワード")],
    category: Annotated[str | None, Field(description="カテゴリフィルタ")] = None,
    limit: Annotated[int, Field(description="最大件数")] = 20,
) -> dict:
    """メモをキーワードで全文検索する（FTS5）。"""
    db = _get_db()
    result = db.search_memories(query, category, limit)
    logger.info("Search memories: query='%s', results=%d", query, len(result["results"]))
    return result


@mcp.tool()
def list_sessions(
    limit: Annotated[int, Field(description="最大件数")] = 50,
    offset: Annotated[int, Field(description="オフセット")] = 0,
) -> dict:
    """セッション一覧を取得する。"""
    db = _get_db()
    result = db.list_sessions(limit, offset)
    logger.info("List sessions: total=%d, returned=%d", result["total"], len(result["sessions"]))
    return result


if __name__ == "__main__":
    logger.info("KBLite MCP Server starting...")
    mcp.run(transport="stdio")
