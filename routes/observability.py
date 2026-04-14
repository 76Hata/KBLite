"""Observability ダッシュボード API

~/.claude/observability/ 配下の JSONL ログを集計して返す。
LLM使用量は SQLite の llm_usage_logs テーブルから集計する。
"""
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from deps import logger

_SQLITE_PATH = os.getenv("SQLITE_PATH", "/app/data/sqlite/ka.db")

_OBS_DIR = Path.home() / ".claude" / "observability"

_JST = timezone(timedelta(hours=9))


def _parse_date_range(request: Request) -> tuple[str | None, str | None, int]:
    """from/to/days パラメータを解析する。
    Returns: (since_utc, until_utc, days_for_fill)
      - from/to 指定時: JST日付をUTC文字列に変換して返す
      - 未指定時: (None, None, days) を返す
    """
    date_from = request.query_params.get("from", "")  # YYYY-MM-DD (JST)
    date_to = request.query_params.get("to", "")      # YYYY-MM-DD (JST)
    days = int(request.query_params.get("days", "7"))

    if date_from or date_to:
        # JST の日付をUTCに変換
        if date_from:
            jst_start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=_JST)
            since_utc = jst_start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        else:
            since_utc = None
        if date_to:
            jst_end = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=_JST
            )
            until_utc = jst_end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        else:
            until_utc = None
        # 日別穴埋め用の日数を計算
        if date_from and date_to:
            delta = (datetime.strptime(date_to, "%Y-%m-%d")
                     - datetime.strptime(date_from, "%Y-%m-%d")).days + 1
        elif date_from:
            delta = (datetime.now(_JST).date()
                     - datetime.strptime(date_from, "%Y-%m-%d").date()).days + 1
        else:
            delta = days
        return since_utc, until_utc, max(delta, 1)

    return None, None, min(days, 90)


def _utc_to_jst(utc_str: str) -> str:
    """UTC文字列 'YYYY-MM-DD HH:MM:SS' を JST に変換する。"""
    if not utc_str:
        return utc_str
    try:
        utc_dt = datetime.strptime(utc_str[:19], "%Y-%m-%d %H:%M:%S")
        jst_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone(_JST)
        return jst_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, IndexError):
        return utc_str


def _parse_event_ts(ts_str: str) -> datetime | None:
    """ISO 8601 タイムスタンプを timezone-aware datetime に変換する。"""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def _parse_jsonl(path: Path, since: datetime | None = None) -> list[dict]:
    """JSONL ファイルからイベントリストを読み込む。"""
    events: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if since:
                        ev_dt = _parse_event_ts(ev.get("ts", ""))
                        if ev_dt and ev_dt < since:
                            continue
                    events.append(ev)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return events


def _load_events(days: int = 7, since_dt: datetime | None = None) -> list[dict]:
    """指定期間分の全イベントを読み込む。"""
    if not _OBS_DIR.is_dir():
        return []

    if since_dt is None:
        since_dt = datetime.now(_JST) - timedelta(days=days)
    events: list[dict] = []

    for p in sorted(_OBS_DIR.glob("*.jsonl")):
        events.extend(_parse_jsonl(p, since_dt))
    # ローテーション済みファイル（.jsonl.1 等）も読む
    for p in sorted(_OBS_DIR.glob("*.jsonl.*")):
        events.extend(_parse_jsonl(p, since_dt))

    return events


async def get_observability_stats(request: Request) -> JSONResponse:
    """Observability 集計データを返す。"""
    try:
        since_utc, until_utc, days = _parse_date_range(request)

        # from 指定がある場合はそれを使う（UTC aware datetime）
        since_dt = None
        if since_utc:
            since_dt = datetime.strptime(since_utc[:19], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )

        events = _load_events(days, since_dt)

        # to 指定がある場合はイベントをフィルタ（proper datetime comparison）
        if until_utc:
            until_dt = datetime.strptime(until_utc[:19], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            events = [ev for ev in events
                      if (_parse_event_ts(ev.get("ts", "")) or datetime.min.replace(
                          tzinfo=timezone.utc)) <= until_dt]

        if not events:
            return JSONResponse({
                "days": days,
                "total_events": 0,
                "tool_counts": {},
                "event_counts": {},
                "daily_counts": {},
                "hourly_distribution": {},
                "top_tools": [],
                "client_counts": {},
                "recent_events": [],
            })

        # ── 集計 ──
        tool_counter: Counter = Counter()
        event_counter: Counter = Counter()
        daily_counter: Counter = Counter()
        hourly_counter: Counter = Counter()
        client_counter: Counter = Counter()

        for ev in events:
            tool = ev.get("tool", "")
            event_type = ev.get("event", "unknown")
            ts = ev.get("ts", "")
            client = ev.get("client", "")

            if tool:
                tool_counter[tool] += 1
            event_counter[event_type] += 1
            if client:
                client_counter[client] += 1

            if ts:
                # 日別集計
                day = ts[:10]  # YYYY-MM-DD
                daily_counter[day] += 1
                # 時間帯別集計
                try:
                    hour = ts[11:13]
                    hourly_counter[hour] += 1
                except (IndexError, ValueError):
                    pass

        # 日別を全日埋める（0件の日もキーを作る）
        date_to_param = request.query_params.get("to", "")
        if date_to_param:
            end_date = datetime.strptime(date_to_param, "%Y-%m-%d")
        else:
            end_date = datetime.now(_JST)
        daily_filled = {}
        for i in range(days):
            d = (end_date - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_filled[d] = daily_counter.get(d, 0)

        # 時間帯を0-23で埋める
        hourly_filled = {f"{h:02d}": hourly_counter.get(f"{h:02d}", 0) for h in range(24)}

        return JSONResponse({
            "days": days,
            "total_events": len(events),
            "tool_counts": dict(tool_counter.most_common()),
            "event_counts": dict(event_counter),
            "daily_counts": daily_filled,
            "hourly_distribution": hourly_filled,
            "top_tools": tool_counter.most_common(10),
            "client_counts": dict(client_counter.most_common()),
            "recent_events": events[-500:][::-1],  # 直近500件（新しい順）
        })

    except Exception as e:
        logger.exception("observability stats error")
        return JSONResponse({"error": str(e)}, status_code=500)


# ── LLM 使用量集計 ──────────────────────────────────────────────

_MODEL_DISPLAY_NAMES = {
    "claude-opus-4-6": "Opus",
    "claude-opus-4-5": "Opus 4.5",
    "claude-sonnet-4-6": "Sonnet",
    "claude-sonnet-4-5-20241022": "Sonnet 3.5",
    "claude-haiku-4-5-20251001": "Haiku",
}


async def get_llm_usage_stats(request: Request) -> JSONResponse:
    """LLM 使用量の集計データを返す。"""
    try:
        since_utc, until_utc, days = _parse_date_range(request)

        conn = sqlite3.connect(_SQLITE_PATH)
        conn.row_factory = sqlite3.Row

        # テーブル存在チェック
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_usage_logs'"
        ).fetchone()
        if not table_exists:
            conn.close()
            return JSONResponse({
                "days": days, "total_calls": 0, "by_model": {},
                "daily": {}, "total_tokens": {}, "total_cost_usd": 0,
                "recent": [],
            })

        # 期間指定 or N日間
        if since_utc and until_utc:
            rows = conn.execute(
                "SELECT * FROM llm_usage_logs WHERE created_at >= ? AND created_at <= ? ORDER BY created_at DESC",
                (since_utc, until_utc),
            ).fetchall()
        elif since_utc:
            rows = conn.execute(
                "SELECT * FROM llm_usage_logs WHERE created_at >= ? ORDER BY created_at DESC",
                (since_utc,),
            ).fetchall()
        elif until_utc:
            rows = conn.execute(
                "SELECT * FROM llm_usage_logs WHERE created_at <= ? ORDER BY created_at DESC",
                (until_utc,),
            ).fetchall()
        else:
            since = (datetime.now(_JST) - timedelta(days=days)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            rows = conn.execute(
                "SELECT * FROM llm_usage_logs WHERE created_at >= ? ORDER BY created_at DESC",
                (since,),
            ).fetchall()
        conn.close()

        if not rows:
            return JSONResponse({
                "days": days, "total_calls": 0, "by_model": {},
                "daily": {}, "total_tokens": {}, "total_cost_usd": 0,
                "recent": [],
            })

        # ── モデ��別集計 ──
        by_model: dict[str, dict] = defaultdict(lambda: {
            "calls": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_creation_tokens": 0,
            "total_cost_usd": 0.0, "total_duration_ms": 0,
        })
        # ── 日別集計 ──
        daily: dict[str, dict] = defaultdict(lambda: {
            "calls": 0, "input_tokens": 0, "output_tokens": 0,
            "total_cost_usd": 0.0,
        })
        total_cost = 0.0
        total_input = 0
        total_output = 0
        total_cache_read = 0

        for r in rows:
            model = r["model"] or "unknown"
            display = _MODEL_DISPLAY_NAMES.get(model, model)
            m = by_model[display]
            m["calls"] += 1
            m["input_tokens"] += r["input_tokens"] or 0
            m["output_tokens"] += r["output_tokens"] or 0
            m["cache_read_tokens"] += r["cache_read_tokens"] or 0
            m["cache_creation_tokens"] += r["cache_creation_tokens"] or 0
            m["total_cost_usd"] += r["total_cost_usd"] or 0.0
            m["total_duration_ms"] += r["duration_ms"] or 0

            day = _utc_to_jst(r["created_at"] or "")[:10]
            if day:
                d = daily[day]
                d["calls"] += 1
                d["input_tokens"] += r["input_tokens"] or 0
                d["output_tokens"] += r["output_tokens"] or 0
                d["total_cost_usd"] += r["total_cost_usd"] or 0.0

            total_cost += r["total_cost_usd"] or 0.0
            total_input += r["input_tokens"] or 0
            total_output += r["output_tokens"] or 0
            total_cache_read += r["cache_read_tokens"] or 0

        # 日別を全日埋める
        date_to_param = request.query_params.get("to", "")
        if date_to_param:
            end_date = datetime.strptime(date_to_param, "%Y-%m-%d")
        else:
            end_date = datetime.now(_JST)
        daily_filled = {}
        for i in range(days):
            d = (end_date - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_filled[d] = daily.get(d, {
                "calls": 0, "input_tokens": 0, "output_tokens": 0,
                "total_cost_usd": 0.0,
            })

        # 直近レコード（全件）
        recent = []
        for r in rows:
            model = r["model"] or "unknown"
            recent.append({
                "task_id": r["task_id"],
                "model": _MODEL_DISPLAY_NAMES.get(model, model),
                "input_tokens": r["input_tokens"] or 0,
                "output_tokens": r["output_tokens"] or 0,
                "cache_read_tokens": r["cache_read_tokens"] or 0,
                "total_cost_usd": r["total_cost_usd"] or 0.0,
                "duration_ms": r["duration_ms"] or 0,
                "num_turns": r["num_turns"] or 0,
                "client": r["client"] or "",
                "created_at": _utc_to_jst(r["created_at"] or ""),
            })

        return JSONResponse({
            "days": days,
            "total_calls": len(rows),
            "by_model": dict(by_model),
            "daily": daily_filled,
            "total_tokens": {
                "input": total_input,
                "output": total_output,
                "cache_read": total_cache_read,
            },
            "total_cost_usd": round(total_cost, 4),
            "recent": recent,
        })

    except Exception as e:
        logger.exception("llm usage stats error")
        return JSONResponse({"error": str(e)}, status_code=500)
