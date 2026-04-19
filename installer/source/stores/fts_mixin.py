"""FTS5 全文検索 Mixin — SQLite FTS5 による RAG 的検索機能"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class FtsMixin:
    """conversations テーブルに対する FTS5 全文検索"""

    def _init_fts(self):
        """FTS5 仮想テーブルとトリガーを作成する"""
        self._conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
                question,
                answer,
                title,
                content='conversations',
                content_rowid='rowid',
                tokenize='unicode61'
            );

            -- INSERT トリガー
            CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
                INSERT INTO conversations_fts(rowid, question, answer, title)
                VALUES (new.rowid, new.question, new.answer, new.title);
            END;

            -- DELETE トリガー
            CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
                INSERT INTO conversations_fts(conversations_fts, rowid, question, answer, title)
                VALUES ('delete', old.rowid, old.question, old.answer, old.title);
            END;

            -- UPDATE トリガー
            CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
                INSERT INTO conversations_fts(conversations_fts, rowid, question, answer, title)
                VALUES ('delete', old.rowid, old.question, old.answer, old.title);
                INSERT INTO conversations_fts(rowid, question, answer, title)
                VALUES (new.rowid, new.question, new.answer, new.title);
            END;
        """)
        self._conn.commit()
        logger.info("FTS5 仮想テーブル・トリガー初期化完了")

    def rebuild_fts_index(self) -> int:
        """既存の conversations データから FTS5 インデックスを再構築する"""
        self._conn.execute(
            "INSERT INTO conversations_fts(conversations_fts) VALUES ('rebuild')"
        )
        self._conn.commit()
        count = self._conn.execute("SELECT COUNT(*) FROM conversations_fts").fetchone()[0]
        logger.info("FTS5 インデックス再構築完了: %d 件", count)
        return count

    def fts_search(
        self,
        query: str,
        limit: int = 5,
        session_ids: list[str] | None = None,
    ) -> list[dict]:
        """FTS5 で会話を検索し、BM25 スコア順で返す"""
        if not query or not query.strip():
            return []

        fts_query = self._build_fts_query(query)
        if not fts_query:
            return []

        params: list[Any] = [fts_query]

        sql = """
            SELECT
                c.id,
                c.session_id,
                c.sequence,
                c.question,
                c.answer,
                c.title,
                c.summary,
                c.created_at,
                rank
            FROM conversations_fts
            JOIN conversations c ON c.rowid = conversations_fts.rowid
            WHERE conversations_fts MATCH ?
        """

        if session_ids:
            placeholders = ",".join("?" * len(session_ids))
            sql += f" AND c.session_id IN ({placeholders})"
            params.extend(session_ids)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        try:
            cursor = self._conn.execute(sql, params)
        except Exception as e:
            logger.warning("FTS5 検索エラー (query=%s): %s", fts_query, e)
            return []

        results = []
        for row in cursor.fetchall():
            snippet_q = (row["question"] or "")[:200]
            snippet_a = (row["answer"] or "")[:500]
            results.append({
                "id": row["id"],
                "session_id": row["session_id"],
                "sequence": row["sequence"],
                "question": snippet_q,
                "answer": snippet_a,
                "title": row["title"] or "",
                "summary": row["summary"] or "",
                "created_at": row["created_at"],
                "score": abs(row["rank"]),
            })
        return results

    def fts_search_for_rag(
        self,
        query: str,
        limit: int = 3,
        current_session_id: str | None = None,
    ) -> list[dict]:
        """RAG コンテキスト注入用の検索。現在のセッションを除外する"""
        if not query or not query.strip():
            return []

        fts_query = self._build_fts_query(query)
        if not fts_query:
            return []

        params: list[Any] = [fts_query]

        sql = """
            SELECT
                c.id,
                c.session_id,
                c.sequence,
                c.question,
                c.answer,
                c.title,
                c.summary,
                c.created_at,
                s.title as session_title,
                rank
            FROM conversations_fts
            JOIN conversations c ON c.rowid = conversations_fts.rowid
            JOIN sessions s ON c.session_id = s.id
            WHERE conversations_fts MATCH ?
              AND length(c.answer) > 150
        """

        if current_session_id:
            sql += " AND c.session_id != ?"
            params.append(current_session_id)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        try:
            cursor = self._conn.execute(sql, params)
        except Exception as e:
            logger.warning("FTS5 RAG検索エラー (query=%s): %s", fts_query, e)
            return []

        results = []
        for row in cursor.fetchall():
            results.append({
                "session_title": row["session_title"] or "",
                "question": (row["question"] or "")[:200],
                "answer": (row["answer"] or "")[:800],
                "title": row["title"] or "",
                "summary": row["summary"] or "",
                "created_at": row["created_at"],
                "score": abs(row["rank"]),
            })
        return results

    @staticmethod
    def _build_fts_query(user_input: str) -> str:
        """ユーザー入力を FTS5 クエリに変換する。

        各トークンを OR で結合し、部分一致を許容する。
        特殊文字はエスケープする。
        """
        tokens = user_input.split()
        safe_tokens = []
        for t in tokens:
            cleaned = "".join(ch for ch in t if ch.isalnum() or ch in "ぁ-んァ-ヶ亜-熙々〇")
            if cleaned:
                safe_tokens.append(f'"{cleaned}"')
        if not safe_tokens:
            return ""
        return " OR ".join(safe_tokens)

    def fts_stats(self) -> dict:
        """FTS5 インデックスの統計情報を返す"""
        try:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM conversations_fts"
            ).fetchone()[0]
            conv_count = self._conn.execute(
                "SELECT COUNT(*) FROM conversations"
            ).fetchone()[0]
            return {
                "fts_indexed": count,
                "conversations_total": conv_count,
                "in_sync": count == conv_count,
            }
        except Exception as e:
            return {"error": str(e)}
