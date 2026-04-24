"""タスク管理サービス層 — バリデーションと Store 呼び出しを一手に引き受ける。

ルーター層（routes/task.py）は HTTP 変換のみを行い、業務ルールはすべてここに集約する。
例外は TaskValidationError / TaskNotFoundError で返し、ルーター側でステータスコードに翻訳する。
"""

from __future__ import annotations

from typing import Any

from models.task import (
    Task,
    TaskNote,
    TaskNotFoundError,
    coerce_priority,
    coerce_scope,
    coerce_source,
    require_note,
    require_title,
    validate_status,
)


class TaskService:
    """tasks / task_notes の業務ロジックを提供する。

    `store` は SQLiteStore 相当の Store オブジェクトで、TaskMixin のメソッドを備える。
    """

    # update_task で許可するフィールド（status は別途 validate）
    UPDATE_ALLOWED_FIELDS: frozenset[str] = frozenset(
        {"title", "description", "status", "priority", "session_id", "due_date", "scope"}
    )

    def __init__(self, store: Any) -> None:
        self._store = store

    # ── 一覧・取得 ────────────────────────────────────────────
    def list_tasks(
        self,
        *,
        status: str | None = None,
        session_id: str | None = None,
        scope: str | None = None,
        source: str | None = None,
    ) -> list[Task]:
        return self._store.list_tasks(status=status, session_id=session_id, scope=scope, source=source)

    def get_task(self, task_id: str) -> Task:
        task = self._store.get_task(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        task["notes"] = self._store._list_notes_for(task_id)
        return task

    # ── 作成 ──────────────────────────────────────────────────
    def create_task(self, payload: dict) -> Task:
        title = require_title(payload.get("title"))
        description = str(payload.get("description") or "").strip()
        priority = coerce_priority(payload.get("priority"))
        scope = coerce_scope(payload.get("scope"))
        source = coerce_source(payload.get("source"))
        session_id = payload.get("session_id") or None
        due_date = payload.get("due_date") or None

        return self._store.create_task(
            title=title,
            description=description,
            priority=priority,
            session_id=session_id,
            due_date=due_date,
            scope=scope,
            source=source,
        )

    # ── 更新 ──────────────────────────────────────────────────
    def update_task(self, task_id: str, payload: dict) -> Task:
        updates = {k: v for k, v in payload.items() if k in self.UPDATE_ALLOWED_FIELDS}
        if "status" in updates:
            updates["status"] = validate_status(updates["status"])

        task = self._store.update_task(task_id, **updates)
        if task is None:
            raise TaskNotFoundError(task_id)
        task["notes"] = self._store._list_notes_for(task_id)
        return task

    # ── 削除 ──────────────────────────────────────────────────
    def delete_task(self, task_id: str) -> None:
        if not self._store.delete_task(task_id):
            raise TaskNotFoundError(task_id)

    # ── ノート追加 ────────────────────────────────────────────
    def add_task_note(self, task_id: str, payload: dict) -> TaskNote:
        note = require_note(payload.get("note"))
        if self._store.get_task(task_id) is None:
            raise TaskNotFoundError(task_id)
        return self._store.add_task_note(task_id, note)
