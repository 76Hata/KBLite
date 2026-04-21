#!/usr/bin/env python3
"""KBLite statusline script — rate_limits を JSON ファイルに書き出し、
ステータスラインにも表示する。

Claude Code v2.1.80+ が stdin に渡す JSON から rate_limits を取得し:
  1. <kblite_root>/data/sqlite/rate-limits.json に書き出し
     → KBLite が読み取り、Limitゲージに表示
  2. stdout に整形済み文字列を出力 → ターミナルのステータスバーに表示
  3. Weekly バジェット超過時に推奨モデルを書き出し
"""

import json
import math
import sys
import time
from pathlib import Path

# このスクリプトが置かれているディレクトリ(kbliteルート)基準でパスを解決
_OUT_PATH = Path(__file__).parent / "data" / "sqlite" / "rate-limits.json"

_DAILY_RATE = 100 / 7  # ≒14.28%
_SONNET = "claude-sonnet-4-6"
_OPUS = "claude-opus-4-7"


def _bar(pct: float, width: int = 8) -> str:
    filled = round(pct / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _calc_budget_model(used_pct: float, resets_at) -> str:
    """残日数 × daily_rate <= 使用率 → Sonnet 推奨"""
    if resets_at is None or used_pct is None:
        return _OPUS
    try:
        reset_ts = float(resets_at)
        if reset_ts < 1e12:
            reset_ts *= 1000  # 秒→ミリ秒
        remain_ms = reset_ts - time.time() * 1000
        if remain_ms <= 0:
            return _OPUS
        remain_days = math.ceil(remain_ms / 86400000)
        threshold = remain_days * _DAILY_RATE
        return _SONNET if used_pct >= threshold else _OPUS
    except (ValueError, TypeError):
        return _OPUS


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    rate_limits = data.get("rate_limits")
    if not rate_limits:
        return

    # バジェットモデル判定
    seven = rate_limits.get("seven_day", {})
    budget_model = _calc_budget_model(
        seven.get("used_percentage"),
        seven.get("resets_at"),
    )
    rate_limits["recommended_model"] = budget_model

    # JSON ファイルに書き出し（KBLite 向け）
    try:
        _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OUT_PATH.write_text(json.dumps(rate_limits, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

    # ステータスライン文字列を stdout に出力
    parts = []
    five = rate_limits.get("five_hour", {})

    if "used_percentage" in five:
        pct = five["used_percentage"]
        parts.append(f"5h {_bar(pct)} {pct:.0f}%")

    if "used_percentage" in seven:
        pct = seven["used_percentage"]
        model_tag = " [SONNET]" if budget_model == _SONNET else ""
        parts.append(f"7d {_bar(pct)} {pct:.0f}%{model_tag}")

    ctx = data.get("context_window", {})
    if "used_percentage" in ctx:
        pct = ctx["used_percentage"]
        parts.append(f"ctx {_bar(pct)} {pct:.0f}%")

    if parts:
        print(" | ".join(parts))


if __name__ == "__main__":
    main()
