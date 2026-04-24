"""Mixin 共通基底クラス — mypy が _conn 等の共有属性を認識するためのスタブ"""

import sqlite3
from typing import Any


class StoreMixinBase:
    """各 Mixin が依存する属性・メソッドを宣言し、mypy の attr-defined エラーを解消する。

    SQLiteStore が _conn を設定し、_session_to_dict 等を実装するため
    ランタイムではこのクラスのメソッドが呼ばれることはない。
    """

    _conn: sqlite3.Connection

    def _session_to_dict(self, row: Any) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _project_to_dict(row: Any) -> dict[str, Any]:
        raise NotImplementedError

    def update_session(
        self,
        session_id: str,
        title: str | None = None,
        message_count: int | None = None,
        project_id: str | None = None,
        bookmarked: bool | None = None,
        touch_updated_at: bool = True,
    ) -> None:
        raise NotImplementedError
