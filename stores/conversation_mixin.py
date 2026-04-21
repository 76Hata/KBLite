"""会話操作 Mixin"""

import logging
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)


class ConversationMixin:
    """conversations テーブルに対する CRUD・検索操作"""

    def save_conversation(
        self, session_id: str, sequence: int, question: str, answer: str, title: str = "", summary: str = ""
    ) -> str:
        from datetime import datetime

        # 同一セッション内で同じ question+answer が既に存在する場合はスキップ
        dup = self._conn.execute(
            """SELECT id, sequence FROM conversations
               WHERE session_id = ? AND question = ? AND answer = ?
               LIMIT 1""",
            (session_id, question, answer),
        ).fetchone()
        if dup is not None:
            logger.info(
                "Duplicate detected: session=%s existing_seq=%d new_seq=%d — skipped",
                session_id,
                dup["sequence"],
                sequence,
            )
            return dup["id"]

        now = datetime.now(UTC).isoformat()
        conv_id = f"conv_{session_id}_{sequence}"
        self._conn.execute(
            """INSERT OR REPLACE INTO conversations
               (id, session_id, sequence, question, answer, title, summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv_id, session_id, sequence, question, answer, title, summary, now),
        )
        self._conn.commit()
        logger.info("Saved conversation %s (seq=%d)", conv_id, sequence)
        return conv_id

    def get_conversations(self, session_id: str) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? ORDER BY sequence",
            (session_id,),
        )
        items = []
        for row in cursor.fetchall():
            item: dict[str, Any] = {
                "id": row["id"],
                "answer": row["answer"],
                "question": row["question"],
                "sequence": row["sequence"],
                "created_at": row["created_at"],
            }
            if row["title"]:
                item["title"] = row["title"]
            if row["summary"]:
                item["summary"] = row["summary"]
            items.append(item)
        return items

    def update_conversation(
        self, conv_id: str, question: str | None = None, answer: str | None = None
    ) -> None:
        cursor = self._conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"会話が見つかりません: {conv_id}")
        fields: list[str] = []
        params: list[str] = []
        if question is not None:
            fields.append("question = ?")
            params.append(question)
        if answer is not None:
            fields.append("answer = ?")
            params.append(answer)
        if not fields:
            return
        params.append(conv_id)
        self._conn.execute(f"UPDATE conversations SET {', '.join(fields)} WHERE id = ?", params)
        self._conn.commit()
        logger.info("Updated conversation content: %s", conv_id)

    def update_conversation_title(self, conv_id: str, title: str) -> None:
        cursor = self._conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"会話が見つかりません: {conv_id}")
        self._conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conv_id))
        self._conn.commit()
        logger.info("Updated conversation title: %s -> '%s'", conv_id, title)

    def search_conversations_text(
        self,
        keywords: list[str],
        session_ids: list[str] | None = None,
        limit: int = 5,
        exclude_categories: list[str] | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list[Any] = []
        for kw in keywords:
            conditions.append("(c.answer LIKE ? OR c.question LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%"])

        # exclude_categories 指定時は sessions テーブルと JOIN し
        # ロック対象カテゴリのセッションを除外する
        if exclude_categories:
            sql = (
                "SELECT c.* FROM conversations c"
                " JOIN sessions s ON c.session_id = s.id"
                f" WHERE {' AND '.join(conditions)}"
            )
            # カテゴリによる除外
            cat_ph = ",".join("?" * len(exclude_categories))
            sql += f" AND s.category NOT IN ({cat_ph})"
            params.extend(exclude_categories)
            # confidential フラグによる除外
            sql += " AND COALESCE(c.confidential, 0) = 0"
        else:
            sql = f"SELECT c.* FROM conversations c WHERE {' AND '.join(conditions)}"

        if session_ids:
            placeholders = ",".join("?" * len(session_ids))
            sql += f" AND c.session_id IN ({placeholders})"
            params.extend(session_ids)

        sql += " ORDER BY c.created_at DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(sql, params)
        results = []
        for row in cursor.fetchall():
            meta: dict[str, Any] = {
                "session_id": row["session_id"],
                "sequence": row["sequence"],
                "question": row["question"],
                "created_at": row["created_at"],
            }
            if row["title"]:
                meta["title"] = row["title"]
            results.append(
                {
                    "collection": "kb_conversations",
                    "document": (row["answer"] or "")[:500],
                    "metadata": meta,
                    "distance": 0.0,
                }
            )
        return results

    def search_by_session_id(self, session_id: str, sequence: int | None = None) -> list[dict]:
        results: list[dict] = []
        errors: list[str] = []

        try:
            if sequence is not None:
                cursor = self._conn.execute(
                    "SELECT * FROM conversations WHERE session_id = ? AND sequence = ?",
                    (session_id, sequence),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM conversations WHERE session_id = ? ORDER BY sequence",
                    (session_id,),
                )
            for row in cursor.fetchall():
                meta: dict[str, Any] = {
                    "session_id": row["session_id"],
                    "sequence": row["sequence"],
                    "question": row["question"],
                    "created_at": row["created_at"],
                }
                if row["title"]:
                    meta["title"] = row["title"]
                results.append(
                    {
                        "collection": "kb_conversations",
                        "document": row["answer"] or "",
                        "metadata": meta,
                        "distance": 0.0,
                    }
                )
        except Exception as e:
            msg = f"conversations 検索エラー: {e}"
            logger.warning(msg)
            errors.append(msg)

        try:
            cursor = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                meta_s = self._session_to_dict(row)
                results.append(
                    {
                        "collection": "kb_sessions",
                        "document": row["title"] or "",
                        "metadata": meta_s,
                        "distance": 0.0,
                    }
                )
        except Exception as e:
            msg = f"sessions 検索エラー: {e}"
            logger.warning(msg)
            errors.append(msg)

        if not results and errors:
            return [
                {
                    "collection": "_error",
                    "document": "; ".join(errors),
                    "metadata": {"session_id": session_id},
                    "distance": -1.0,
                }
            ]

        return results
