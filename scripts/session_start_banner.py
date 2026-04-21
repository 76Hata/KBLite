#!/usr/bin/env python3
"""SessionStart hook — 未完了の大きな案件（scope=global）を冒頭に提示する。

Claude Code の SessionStart hook から呼ばれる想定。
stdout に Markdown を出力すると、Claude Code はそれをセッション冒頭コンテキストとして
読み込む（hook 仕様による）。

環境変数:
    SQLITE_PATH : KBLite の SQLite ファイルパス
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "sqlite" / "kblite.db"
_DB_PATH = Path(os.getenv("SQLITE_PATH", str(_DEFAULT_DB)))

_LIMIT_GLOBAL = 10
_LIMIT_SESSION = 5


def _build_banner() -> str:
    if not _DB_PATH.exists():
        return ""

    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return ""

    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "scope" not in cols or "source" not in cols:
            return ""  # マイグレーション未実施

        globals_rows = conn.execute(
            """SELECT id, title, status, priority, description, updated_at
                 FROM tasks
                WHERE scope = 'global' AND status IN ('todo','in_progress')
                ORDER BY CASE status WHEN 'in_progress' THEN 0 ELSE 1 END,
                         CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                         updated_at DESC
                LIMIT ?""",
            (_LIMIT_GLOBAL,),
        ).fetchall()

        sessions_rows = conn.execute(
            """SELECT id, title, status, updated_at
                 FROM tasks
                WHERE scope = 'session' AND status = 'in_progress'
                ORDER BY updated_at DESC
                LIMIT ?""",
            (_LIMIT_SESSION,),
        ).fetchall()
    finally:
        conn.close()

    if not globals_rows and not sessions_rows:
        return ""

    lines: list[str] = []
    lines.append("## 前回からの引き継ぎタスク（kblite-tasks）")
    lines.append("")

    if globals_rows:
        lines.append("### 大きな案件（scope=global）")
        for r in globals_rows:
            badge = "[進行中]" if r["status"] == "in_progress" else "[未着手]"
            prio = r["priority"] or "normal"
            p_badge = {"high": "★高", "normal": "中", "low": "▽低"}.get(prio, prio)
            lines.append(f"- {badge} **{r['title']}** (優先度:{p_badge}) — id:`{r['id']}`")
            if r["description"]:
                desc = r["description"]
                if len(desc) > 80:
                    desc = desc[:77] + "..."
                lines.append(f"  - {desc}")
        lines.append("")

    if sessions_rows:
        lines.append("### セッション内進行中タスク（TodoWrite由来・参考）")
        for r in sessions_rows:
            lines.append(f"- [進行中] {r['title']}")
        lines.append("")

    lines.append(
        "> 大きな案件は `kblite-tasks` MCP（`task_update`/`task_add_note`）で管理し、"
        "今回のセッション内の細かい進捗は TodoWrite を使ってください。"
    )
    return "\n".join(lines)


def main() -> int:
    try:
        banner = _build_banner()
    except Exception as e:
        print(f"[session_start_banner] error: {e}", file=sys.stderr)
        return 0
    if banner:
        # UTF-8 で確実に出す
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        print(banner)
    return 0


if __name__ == "__main__":
    sys.exit(main())
