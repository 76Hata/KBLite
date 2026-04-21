#!/usr/bin/env python3
"""PostToolUse hook: 権限ブロック → KBLite 権限申請バナー

Claude Code がツール呼び出しを権限不足でブロックした際に、
KBLite の権限申請 API へ自動投稿し、KBブラウザ上のバナーに表示する。

設定例 (~/.claude/settings.json):
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Write|Edit|Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python C:\\\\01_Develop\\\\project\\\\kblite\\\\scripts\\\\perm_request_hook.py"
                    }
                ]
            }
        ]
    }
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

KBLITE_URL = "http://localhost:8080/api/permissions/requests"


def _to_forward_slash(path: str) -> str:
    """Windows バックスラッシュ → フォワードスラッシュ変換。"""
    return path.replace("\\", "/")


def _make_pattern(tool_name: str, tool_input: dict) -> str | None:
    """ブロックされたツール呼び出しから Claude Code 権限パターン文字列を生成する。

    Args:
        tool_name: ツール名 (Write / Edit / Bash 等)
        tool_input: ツール引数 dict

    Returns:
        "ToolName(path)" 形式の文字列、または生成不可の場合 None
    """
    if tool_name in ("Write", "Edit"):
        path = tool_input.get("file_path", "").strip()
        if not path:
            return None
        path = _to_forward_slash(path)
        # ホームディレクトリ配下のファイルはディレクトリごと許可するパターンを提案
        try:
            home = Path.home()
            p_abs = Path(path)
            if p_abs.is_relative_to(home):
                # 親ディレクトリ + /** で提案
                parent = _to_forward_slash(str(p_abs.parent))
                return f"{tool_name}({parent}/**)"
        except (ValueError, TypeError):
            pass
        return f"{tool_name}({path})"

    if tool_name == "Bash":
        cmd = tool_input.get("command", "").strip()
        if not cmd:
            return None
        # コマンドが長い場合は先頭100文字で切る
        short = cmd[:100].replace("\n", " ")
        return f"Bash({short})"

    # その他ツール: ツール名のみのワイルドカード
    return f"{tool_name}(*)"


def main() -> None:
    # stdin から Claude Code hook イベントを読む
    try:
        event = json.load(sys.stdin)
    except Exception:
        return  # JSON でない場合は何もしない

    # blocked フラグが立っていない場合はスキップ
    if not event.get("blocked"):
        return

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    pattern = _make_pattern(tool_name, tool_input)
    if not pattern:
        return

    reason = (
        f'Claude Code が "{tool_name}" を実行しようとしましたが権限がありません。'
        f" 許可する場合は「許可」ボタンを押してください。"
    )

    payload = json.dumps(
        {"tool": tool_name, "pattern": pattern, "reason": reason},
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        KBLITE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        urllib.request.urlopen(req, timeout=3)
    except (urllib.error.URLError, OSError):
        # KBLite が起動していない場合は静かに無視する
        pass


if __name__ == "__main__":
    main()
