"""チャット・タスク管理エンドポイント"""

import asyncio
import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from deps import (
    AGENTS,
    AI_SERVICES,
    MODELS,
    TEAMS,
    logger,
    resolve_project_cwd,
)
from prompt import build_team_prompt

# ── LLMルーター（ヒューリスティック — LLM呼び出し不要）────────
_ROUTE_SONNET = "claude-sonnet-4-6"
_ROUTE_OPUS = "claude-opus-4-7"
_MODEL_DISPLAY = {m["id"]: m["name"] for m in MODELS}

_CLI_SAFE = re.compile(r"^[a-zA-Z0-9_.\/-]+$")


def _validate_cli_token(cli: str) -> bool:
    if not cli or ".." in cli:
        return False
    return bool(_CLI_SAFE.fullmatch(cli))


def _default_ai_service_id() -> str:
    for s in AI_SERVICES:
        if s.get("default"):
            return s["id"]
    return AI_SERVICES[0]["id"] if AI_SERVICES else "claude"


def _allowed_ai_service_ids() -> set[str]:
    return {s["id"] for s in AI_SERVICES}


def _resolve_cli_executable(service_id: str) -> str:
    entry = next((s for s in AI_SERVICES if s["id"] == service_id), None)
    if not entry:
        sid = _default_ai_service_id()
        entry = next((s for s in AI_SERVICES if s["id"] == sid), None)
    if not entry:
        return os.getenv("AI_CLI", "claude")
    env_key = f"KA_AI_CLI_{entry['id'].upper().replace('-', '_')}"
    env_override = os.getenv(env_key, "").strip()
    if env_override and _validate_cli_token(env_override):
        return env_override
    cli = (entry.get("cli") or "").strip()
    if not cli:
        if entry["id"] == "claude":
            cli = os.getenv("AI_CLI", "claude")
        elif entry["id"] == "cursor":
            cli = "agent"
        else:
            cli = entry["id"]
    if not _validate_cli_token(cli):
        cli = "claude" if entry["id"] == "claude" else "agent"
    return cli


_OPUS_KEYWORDS = re.compile(
    r"(設計|アーキテクチャ|リファクタ|コードレビュー|パフォーマンス|セキュリティ|脆弱性"
    r"|最適化|デバッグ|実装|ER図|DB設計|システム設計|インフラ|CI/CD|テスト設計"
    r"|要件定義|分析|比較検討|意思決定|戦略|ロードマップ|障害|根本原因)"
)


def _route_model_heuristic(
    message: str,
    agents: list[str],
    attachments: list | None,
    history: list,
) -> tuple[str, str]:
    """アドバイザー戦略: Sonnet（エグゼキューター）を基本とし、
    複雑なタスクと判断した場合のみ Opus（アドバイザー）にルーティングする。

    CLIは API の advisor_20260301 ツールをサポートしないため、
    ヒューリスティックで等価な振り分けを実現する。

    Opus へのルーティング条件（いずれか1つでも該当すれば昇格）:
      1. 添付ファイルあり（ファイル内容の深い分析が必要）
      2. メッセージが 400 文字超（複雑な質問）
      3. 複雑度キーワードを含む（設計・分析・セキュリティ等）
      4. 3エージェント以上のチーム討議
    """
    needs_opus = False
    reason = ""

    if attachments:
        needs_opus = True
        reason = "添付ファイルあり"
    elif len(message) > 400:
        needs_opus = True
        reason = f"長文({len(message)}文字)"
    elif _OPUS_KEYWORDS.search(message):
        needs_opus = True
        reason = "複雑度キーワード検出"
    elif len(agents) >= 3:
        needs_opus = True
        reason = f"チーム討議({len(agents)}エージェント)"

    if needs_opus:
        model_id = _ROUTE_OPUS
        logger.info("ルーター(advisor→Opus): %s | '%s...'", reason, message[:50])
    else:
        model_id = _ROUTE_SONNET
        logger.info("ルーター(advisor→Sonnet): シンプルな質問 | '%s...'", message[:50])

    display = _MODEL_DISPLAY.get(model_id, "Sonnet")
    return model_id, display


# ── クライアント検出 ──────────────────────────────────────────────


def detect_client(user_agent: str) -> str:
    """User-Agent 文字列からクライアント種別を判定して説明文を返す。"""
    if not user_agent:
        return ""
    ua = user_agent.lower()
    # デバイス判定
    if "iphone" in ua:
        device = "iPhone"
    elif "ipad" in ua:
        device = "iPad"
    elif "android" in ua:
        device = "Android"
    elif "windows" in ua:
        device = "Windows PC"
    elif "macintosh" in ua or "mac os" in ua:
        device = "Mac"
    else:
        device = "PC"
    # ブラウザ判定
    if "edg/" in ua:
        browser = "Edge"
    elif "chrome" in ua and "safari" in ua:
        browser = "Chrome"
    elif "safari" in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"
    else:
        browser = "ブラウザ"
    return f"KBブラウザ（{device} / {browser}）"


# ── タスクレジストリ ──────────────────────────────────────────────

_MAX_CONCURRENT_TASKS = 10
_team_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_TASKS)
_concurrent_count = 0
_SEMAPHORE_WAIT_TIMEOUT = 86430
_DEFAULT_CWD = os.getenv("KB_DEFAULT_CWD", str(Path(__file__).parent.parent))
_TASK_TTL = 600  # 10分でタスク結果を破棄

_SQLITE_PATH = os.getenv("SQLITE_PATH", str(Path(__file__).parent.parent / "data" / "sqlite" / "kblite.db"))


class _TaskState:
    def __init__(self):
        self.status = "running"  # running | done | error | cancelled
        self.text = ""
        self.error = ""
        self.queue: asyncio.Queue = asyncio.Queue()
        self.created_at = time.time()
        self.proc: asyncio.subprocess.Process | None = None
        self.web_search_used = False
        # LLM使用量トラッキング（stream-json の system/result イベントから取得）
        self.llm_model = ""
        self.llm_usage: dict = {}
        self.llm_model_usage: dict = {}
        self.llm_cost_usd = 0.0
        self.llm_duration_ms = 0
        self.llm_duration_api_ms = 0
        self.llm_num_turns = 0
        self.claude_session_id = ""  # Claude CLI の session_id（stream-json の result から取得）


_active_tasks: dict[str, _TaskState] = {}


# ── タスク結果の永続化（SQLite）──────────────────────────────────


def _init_task_results_table():
    """task_results テーブルを作成する（存在しなければ）"""
    try:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_results (
                task_id     TEXT PRIMARY KEY,
                status      TEXT NOT NULL,
                text        TEXT DEFAULT '',
                error       TEXT DEFAULT '',
                created_at  TEXT NOT NULL
            )
        """)
        # 古い結果を削除（7日以上前）
        conn.execute("DELETE FROM task_results WHERE created_at < datetime('now', '-7 days')")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("task_results テーブル初期化エラー: %s", e)


_init_task_results_table()


def _init_llm_usage_table():
    """llm_usage_logs テーブルを作成する（存在しなければ）"""
    try:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage_logs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id             TEXT NOT NULL,
                model               TEXT NOT NULL DEFAULT '',
                input_tokens        INTEGER DEFAULT 0,
                output_tokens       INTEGER DEFAULT 0,
                cache_read_tokens   INTEGER DEFAULT 0,
                cache_creation_tokens INTEGER DEFAULT 0,
                total_cost_usd      REAL DEFAULT 0,
                duration_ms         INTEGER DEFAULT 0,
                duration_api_ms     INTEGER DEFAULT 0,
                num_turns           INTEGER DEFAULT 0,
                client              TEXT DEFAULT '',
                model_usage_json    TEXT DEFAULT '{}',
                created_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_usage_created
            ON llm_usage_logs (created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_usage_model
            ON llm_usage_logs (model)
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("llm_usage_logs テーブル初期化エラー: %s", e)


_init_llm_usage_table()


def _resolve_model_name(state: "_TaskState") -> str:
    """モデル名を解決する。systemイベントのmodelが空の場合、model_usageから最もコストの高いモデルを取得する。"""
    if state.llm_model:
        return state.llm_model
    if not state.llm_model_usage:
        return ""
    # model_usage_json から最もコストの高いモデルを主要モデルとして採用
    best_model = ""
    best_cost = -1.0
    for model_id, info in state.llm_model_usage.items():
        cost = info.get("costUSD", 0.0) if isinstance(info, dict) else 0.0
        if cost > best_cost:
            best_cost = cost
            best_model = model_id
    return best_model


def _persist_llm_usage(task_id: str, state: "_TaskState", client: str = ""):
    """LLM使用量をSQLiteに保存する"""
    if not state.llm_model and not state.llm_usage:
        return
    usage = state.llm_usage
    model = _resolve_model_name(state)
    try:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.execute(
            """INSERT INTO llm_usage_logs
               (task_id, model, input_tokens, output_tokens,
                cache_read_tokens, cache_creation_tokens,
                total_cost_usd, duration_ms, duration_api_ms,
                num_turns, client, model_usage_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                model,
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("cache_read_input_tokens", 0),
                usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_creation", {}).get("ephemeral_1h_input_tokens", 0)
                + usage.get("cache_creation", {}).get("ephemeral_5m_input_tokens", 0),
                state.llm_cost_usd,
                state.llm_duration_ms,
                state.llm_duration_api_ms,
                state.llm_num_turns,
                client,
                json.dumps(state.llm_model_usage),
            ),
        )
        conn.commit()
        conn.close()
        logger.info(
            "LLM使用量記録: task=%s, model=%s, in=%d, out=%d, cost=$%.4f",
            task_id,
            state.llm_model,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            state.llm_cost_usd,
        )
    except Exception as e:
        logger.warning("LLM使用量の永続化エラー (task=%s): %s", task_id, e)


def _persist_task_result(task_id: str, status: str, text: str, error: str):
    """完了したタスク結果をSQLiteに保存する"""
    try:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.execute(
            """INSERT OR REPLACE INTO task_results (task_id, status, text, error, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (task_id, status, text, error),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("タスク結果の永続化エラー (task=%s): %s", task_id, e)


def _load_task_result(task_id: str) -> dict | None:
    """SQLiteからタスク結果を読み込む"""
    try:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_results WHERE task_id = ?", (task_id,)).fetchone()
        conn.close()
        if row:
            return {"status": row["status"], "text": row["text"], "error": row["error"]}
    except Exception as e:
        logger.warning("タスク結果の読み込みエラー (task=%s): %s", task_id, e)
    return None


# ── エンドポイント ────────────────────────────────────────────────


async def team_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)

    message = str(body.get("message", "")).strip()
    agents = body.get("agents", [])
    mode = body.get("mode", "team-it")
    _allowed_modes = {t["id"] for t in TEAMS}
    if mode not in _allowed_modes:
        return JSONResponse({"error": f"不正なモード: {mode}"}, status_code=400)
    history = body.get("history", [])
    model = str(body.get("model", "")).strip()
    category = str(body.get("category", "")).strip()
    search_all = bool(body.get("search_all", False))
    workspace_project = str(body.get("workspace_project", "")).strip()
    fork_session_id = str(body.get("fork_session_id", "")).strip()
    current_session_id = str(body.get("session_id", "")).strip()

    _svc_ids = _allowed_ai_service_ids()
    ai_service = str(body.get("ai_service", "")).strip()
    if not ai_service or ai_service not in _svc_ids:
        ai_service = _default_ai_service_id()
    cli_executable = _resolve_cli_executable(ai_service)

    # モデルのバリデーション
    _allowed_models = {m["id"] for m in MODELS}
    if model and model not in _allowed_models:
        model = ""

    # LLMルーティング（「おまかせ」選択時 — ヒューリスティック判定）
    routed_model_name = ""
    if model == "auto":
        model, routed_model_name = _route_model_heuristic(
            message,
            agents,
            body.get("attachments"),
            history,
        )

    if not message:
        return JSONResponse({"error": "message は必須です"}, status_code=400)
    if len(message) > 50000:
        return JSONResponse({"error": "message は 50000 文字以内にしてください"}, status_code=400)

    # 添付ファイル処理（メッセージ長チェック後に結合）
    attachments = body.get("attachments", [])
    if attachments and isinstance(attachments, list):
        text_parts = []
        img_paths = []
        pdf_paths = []
        upload_dir = Path("/tmp/ka_uploads")
        upload_dir.mkdir(exist_ok=True)

        for att in attachments[:5]:  # 最大5ファイル
            name = str(att.get("name", "")).strip()
            content = str(att.get("content", "")).strip()
            att_type = str(att.get("type", "text")).strip()

            if not name or not content:
                continue

            if att_type == "image":
                m = re.match(r"data:(image/[a-z]+);base64,(.*)", content, re.DOTALL)
                if m:
                    ext_map = {
                        "image/png": "png",
                        "image/jpeg": "jpg",
                        "image/gif": "gif",
                        "image/webp": "webp",
                    }
                    ext = ext_map.get(m.group(1), "png")
                    fname = upload_dir / f"{uuid.uuid4().hex}.{ext}"
                    try:
                        fname.write_bytes(base64.b64decode(m.group(2)))
                        img_paths.append((name, str(fname)))
                    except Exception as e:
                        logger.warning("画像の保存に失敗: %s: %s", name, e)
            elif att_type == "pdf":
                m = re.match(r"data:[^;]*;base64,(.*)", content, re.DOTALL)
                if m:
                    fname = upload_dir / f"{uuid.uuid4().hex}.pdf"
                    try:
                        fname.write_bytes(base64.b64decode(m.group(1)))
                        pdf_paths.append((name, str(fname)))
                    except Exception as e:
                        logger.warning("PDFの保存に失敗: %s: %s", name, e)
            else:
                if name and content:
                    text_parts.append(f"### {name}\n```\n{content}\n```")

        prefix_parts = []
        if text_parts:
            prefix_parts.append("## 添付ファイル\n" + "\n\n".join(text_parts))
        if img_paths:
            lines = ["## 添付画像"]
            lines.append(
                "以下の画像ファイルが添付されています。Read ツールで各ファイルを読み込んで内容を解析してください:"
            )
            for orig_name, fpath in img_paths:
                lines.append(f"- {fpath}  （元ファイル名: {orig_name}）")
            prefix_parts.append("\n".join(lines))
        if pdf_paths:
            lines = ["## 添付PDF"]
            lines.append(
                "以下のPDFファイルが添付されています。Read ツールで各ファイルを読み込んで内容を確認してください:"
            )
            for orig_name, fpath in pdf_paths:
                lines.append(f"- {fpath}  （元ファイル名: {orig_name}）")
            prefix_parts.append("\n".join(lines))
        if prefix_parts:
            message = "\n\n".join(prefix_parts) + "\n\n## 質問\n" + message

    # エージェントIDのバリデーション
    valid_ids = {a["id"] for a in AGENTS}
    for agent_id in agents:
        if agent_id not in valid_ids:
            return JSONResponse({"error": f"不正なエージェントID: {agent_id}"}, status_code=400)

    # 古いタスクをクリーンアップ
    now = time.time()
    expired = [
        tid for tid, ts in _active_tasks.items() if ts.status != "running" and now - ts.created_at > _TASK_TTL
    ]
    for tid in expired:
        del _active_tasks[tid]

    # クライアント検出
    client_context = detect_client(request.headers.get("user-agent", ""))

    # プロンプト構築
    lesson_context = ""
    try:
        prompt = build_team_prompt(
            message,
            agents,
            mode,
            history,
            category,
            search_all,
            client_context=client_context,
            lesson_context=lesson_context,
            session_id=current_session_id,
        )
    except FileNotFoundError as e:
        logger.error("エージェント定義エラー: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    # タスクID生成・登録
    task_id = uuid.uuid4().hex[:12]
    task_state = _TaskState()
    _active_tasks[task_id] = task_state

    # プロジェクトCWD解決（Cursor Agent は workspaces-cursor 側を参照）
    project_cwd = resolve_project_cwd(workspace_project, ai_service) if workspace_project else ""

    # バックグラウンドタスクを起動
    asyncio.create_task(
        _run_claude_task(
            task_id,
            task_state,
            prompt,
            mode,
            model,
            project_cwd,
            client_context=client_context,
            cli_executable=cli_executable,
            ai_service=ai_service,
            resume_session_id=fork_session_id,
        )
    )

    async def event_stream():
        first_evt = {"type": "task_id", "task_id": task_id, "ai_service": ai_service}
        # Cursor Agent は KB 側モデル ID を CLI に渡さないため、ルーティング表示は誤解を招く
        if routed_model_name and ai_service != "cursor":
            first_evt["routed_model"] = routed_model_name
        yield f"data: {json.dumps(first_evt)}\n\n"
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(task_state.queue.get(), timeout=15)
                except TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    continue
                if chunk is None:
                    break
                yield f"data: {json.dumps(chunk)}\n\n"
        except asyncio.CancelledError:
            logger.info("SSEクライアント切断 (task=%s), バックグラウンドタスクは継続", task_id)
            return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_FALLBACK_MODEL_MAP = {
    "claude-opus-4-6": "claude-sonnet-4-6",
    "claude-opus-4-5": "claude-sonnet-4-6",
}


def _build_claude_cmd(
    model: str,
    max_turns: int,
    cli_executable: str,
    *,
    ai_service: str = "",
    resume_session_id: str = "",
) -> list[str]:
    """AI CLI コマンドを組み立てる（cli_executable: PATH解決前のコマンド名またはフルパス）

    Cursor 系は --model に Claude Code 用 ID（claude-opus-4-6 等）を渡せないため、
    サービスが cursor またはバイナリ名が agent/cursor のときはモデル引数を付与しない。
    resume_session_id が指定された場合は --resume <id> --fork-session を付与する。
    """
    ai_cli_path = shutil.which(cli_executable) or cli_executable
    cli_name = Path(ai_cli_path).name
    is_cursor_like = cli_name in ("agent", "cursor")
    skip_kb_model_args = is_cursor_like or ai_service == "cursor"
    # Windows では .cmd ファイルを直接 exec できないため cmd /c でラップする
    _cmd_prefix = ["cmd", "/c"] if (sys.platform == "win32" and ai_cli_path.lower().endswith(".cmd")) else []
    cmd = [
        *_cmd_prefix,
        ai_cli_path,
        "-p",
        "--output-format",
        "stream-json",
    ]
    if is_cursor_like:
        # Cursor Agent 側の無人実行向けオプション
        cmd.extend(["--force", "--trust", "--approve-mcps"])
    else:
        cmd.extend(
            [
                "--verbose",
                "--max-turns",
                str(max_turns),
                "--dangerously-skip-permissions",
            ]
        )
    if resume_session_id and not is_cursor_like:
        cmd.extend(["--resume", resume_session_id, "--fork-session"])
    if model and not skip_kb_model_args:
        cmd.extend(["--model", model])
        fallback = _FALLBACK_MODEL_MAP.get(model)
        if fallback:
            cmd.extend(["--fallback-model", fallback])
    return cmd


def _parse_stream_event(line: str, state: _TaskState) -> dict | None:
    """Claude CLI の stream-json 1行をパースし、UIイベントを返す。

    Returns:
        UIイベント dict、または None（UI送信不要の場合）。
        "overloaded" を返した場合は API overloaded を意味する。
    """
    try:
        evt = json.loads(line)
    except (json.JSONDecodeError, KeyError):
        return None

    evt_type = evt.get("type", "")

    # system イベント: モデル情報を取得
    if evt_type == "system":
        state.llm_model = evt.get("model", "")
        return None

    if evt_type == "result":
        # LLM使用量を TaskState に保存
        state.llm_usage = evt.get("usage", {})
        state.llm_model_usage = evt.get("modelUsage", {})
        state.llm_cost_usd = evt.get("total_cost_usd", 0.0) or 0.0
        state.llm_duration_ms = evt.get("duration_ms", 0) or 0
        state.llm_duration_api_ms = evt.get("duration_api_ms", 0) or 0
        state.llm_num_turns = evt.get("num_turns", 0) or 0
        # Claude CLI session_id（--resume --fork-session で利用）
        if evt.get("session_id"):
            state.claude_session_id = evt["session_id"]
        # 完了シグナル（テキストは assistant イベントで既に送信済み）
        return {"type": "_result", "data": evt}

    if evt_type == "error":
        err_info = evt.get("error", {})
        if isinstance(err_info, dict):
            err_type = err_info.get("type", "")
            if err_type == "overloaded_error":
                return {"type": "_overloaded"}
            if err_type == "authentication_error":
                return {"type": "_auth_error", "message": err_info.get("message", "認証エラー")}
        return None

    if evt_type == "assistant":
        content = evt.get("message", {})
        if isinstance(content, dict):
            for block in content.get("content", []):
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block["text"]
                    if state.text and not state.text.endswith("\n") and text and not text.startswith("\n"):
                        sep = "\n\n"
                        state.text += sep + text
                        return {"type": "chunk", "content": sep + text}
                    else:
                        state.text += text
                        return {"type": "chunk", "content": text}
                elif block_type == "tool_use":
                    tool_name = block.get("name", "")
                    if tool_name:
                        if tool_name in ("WebSearch", "WebFetch"):
                            state.web_search_used = True
                        return {"type": "tool_activity", "tool": tool_name}
                elif block_type == "thinking":
                    return {"type": "thinking"}
    return None


async def _run_claude_task(
    task_id: str,
    state: "_TaskState",
    prompt: str,
    mode: str,
    model: str,
    cwd: str = "",
    *,
    client_context: str = "",
    cli_executable: str = "",
    ai_service: str = "",
    resume_session_id: str = "",
):
    """AI CLI を subprocess として実行し、結果を TaskState に蓄積する"""
    global _concurrent_count

    if _concurrent_count >= _MAX_CONCURRENT_TASKS:
        await state.queue.put(
            {
                "type": "waiting",
                "message": f"他のタスクが実行中です（{_concurrent_count}/{_MAX_CONCURRENT_TASKS}件）。順番待ちしています...",
            }
        )

    try:
        await asyncio.wait_for(_team_semaphore.acquire(), timeout=_SEMAPHORE_WAIT_TIMEOUT)
    except TimeoutError:
        state.status = "error"
        state.error = "同時実行の待機がタイムアウトしました。しばらくしてからお試しください。"
        await state.queue.put({"type": "error", "message": state.error})
        await state.queue.put(None)
        return

    _concurrent_count += 1
    try:
        if mode == "fast":
            max_turns = 10
        else:
            max_turns = 100

        effective_cwd = cwd or _DEFAULT_CWD
        eff_cli = cli_executable or _resolve_cli_executable(_default_ai_service_id())
        cmd = _build_claude_cmd(
            model, max_turns, eff_cli, ai_service=ai_service, resume_session_id=resume_session_id
        )

        logger.info(
            "AI CLI実行: task=%s, ai_service=%s, cli=%s, mode=%s, model=%s, max_turns=%d, cwd=%s, fork=%s, concurrent=%d/%d",
            task_id,
            ai_service or "-",
            eff_cli,
            mode,
            model or "(default)",
            max_turns,
            effective_cwd,
            resume_session_id or "-",
            _concurrent_count,
            _MAX_CONCURRENT_TASKS,
        )
        logger.info("AI CLIコマンド全体 (task=%s): %s", task_id, cmd)
        logger.info(
            "CWD存在確認 (task=%s): cwd=%s exists=%s", task_id, effective_cwd, Path(effective_cwd).exists()
        )

        _API_OVERLOAD_MAX_RETRIES = 10
        _API_OVERLOAD_BASE_WAIT = 10
        _API_OVERLOAD_DOWNGRADE_AFTER = 3  # N回失敗後にモデルダウングレード
        api_overload_attempts = 0
        current_cmd = cmd

        while True:
            _api_overloaded = False

            # クライアント情報・サービス種別を環境変数で渡す（CLI / hook が参照可）
            proc_env = None
            if client_context or ai_service:
                proc_env = {**os.environ}
                if client_context:
                    proc_env["KA_CLIENT_CONTEXT"] = client_context
                if ai_service:
                    proc_env["KA_AI_SERVICE"] = ai_service

            # start_new_session はWindows非対応のため CREATE_NEW_PROCESS_GROUP で代替
            _proc_group_kwargs: dict = (
                {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                if sys.platform == "win32"
                else {"start_new_session": True}
            )
            proc = await asyncio.create_subprocess_exec(
                *current_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=effective_cwd,
                env=proc_env,
                limit=1024 * 1024,  # 1MB: Claude CLIの長大JSON行対策
                **_proc_group_kwargs,
            )
            state.proc = proc

            # stderr を非同期で収集するタスク
            stderr_chunks: list[bytes] = []

            async def _drain_stderr():
                try:
                    async for raw in proc.stderr:
                        stderr_chunks.append(raw)
                except Exception:
                    pass

            stderr_task = asyncio.create_task(_drain_stderr())

            # stdin にプロンプトを書き込んで閉じる
            try:
                proc.stdin.write(prompt.encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()
                await proc.stdin.wait_closed()
            except Exception as e:
                logger.error("stdin write error (task=%s): %s", task_id, e)

            # stdout から stream-json を読み取る
            try:
                async for raw_line in proc.stdout:
                    if state.status == "cancelled":
                        break

                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue

                    # overloaded チェック（JSON パース前）
                    if "overloaded_error" in line:
                        _api_overloaded = True
                        logger.warning("API overloaded in stream (task=%s)", task_id)
                        break

                    ui_evt = _parse_stream_event(line, state)
                    if ui_evt is None:
                        continue
                    if ui_evt.get("type") == "_overloaded":
                        _api_overloaded = True
                        break
                    if ui_evt.get("type") == "_auth_error":
                        state.status = "error"
                        state.error = "認証エラー"
                        _persist_task_result(task_id, "error", "", state.error)
                        await state.queue.put(
                            {
                                "type": "auth_error",
                                "message": ui_evt.get(
                                    "message", "APIキーが無効です。認証設定を確認してください。"
                                ),
                            }
                        )
                        await state.queue.put(None)
                        return
                    if ui_evt.get("type") == "_result":
                        break
                    await state.queue.put(ui_evt)
            except Exception as e:
                logger.error("Stream read error (task=%s): %s", task_id, e)

            # プロセス終了待ち
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except TimeoutError:
                proc.kill()
                await proc.wait()

            # stderr 収集完了を待つ
            try:
                await asyncio.wait_for(stderr_task, timeout=3)
            except (TimeoutError, Exception):
                stderr_task.cancel()
            stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
            if stderr_text:
                logger.info("Claude CLI stderr (task=%s): %s", task_id, stderr_text[:500])

            if state.status == "cancelled":
                return

            # stderr からの認証エラー検出
            _AUTH_MARKERS = ("authentication_error", "Invalid authentication credentials", "401")
            if state.status != "error" and any(m in stderr_text for m in _AUTH_MARKERS):
                state.status = "error"
                state.error = "認証エラー"
                _persist_task_result(task_id, "error", "", state.error)
                await state.queue.put(
                    {
                        "type": "auth_error",
                        "message": "APIキーが無効か未設定です。認証設定を確認してください。",
                    }
                )
                await state.queue.put(None)
                return

            # API overloaded → リトライ（指数バックオフ + モデルダウングレード）
            if _api_overloaded:
                api_overload_attempts += 1
                if api_overload_attempts >= _API_OVERLOAD_MAX_RETRIES:
                    state.status = "error"
                    state.error = "APIが混雑しています。しばらく経ってからお試しください。"
                    await state.queue.put({"type": "error", "message": state.error})
                    await state.queue.put(None)
                    return

                # N回失敗後にフォールバックモデルへダウングレード
                if api_overload_attempts == _API_OVERLOAD_DOWNGRADE_AFTER and model:
                    fallback = _FALLBACK_MODEL_MAP.get(model)
                    if fallback:
                        current_cmd = _build_claude_cmd(fallback, max_turns, eff_cli, ai_service=ai_service)
                        logger.warning("モデルダウングレード (task=%s): %s → %s", task_id, model, fallback)
                        await state.queue.put(
                            {
                                "type": "waiting",
                                "message": f"モデルを {fallback} に切り替えてリトライします...",
                            }
                        )
                        await asyncio.sleep(5)
                        continue

                wait_secs = min(_API_OVERLOAD_BASE_WAIT * (2 ** (api_overload_attempts - 1)), 120)
                logger.info(
                    "API overloaded retry (task=%s, %d/%d), %d秒後...",
                    task_id,
                    api_overload_attempts,
                    _API_OVERLOAD_MAX_RETRIES,
                    wait_secs,
                )
                await state.queue.put(
                    {
                        "type": "waiting",
                        "message": f"APIが混雑中です。{wait_secs}秒後にリトライします... ({api_overload_attempts}/{_API_OVERLOAD_MAX_RETRIES})",
                    }
                )
                await asyncio.sleep(wait_secs)
                continue

            break  # 正常終了またはCLI異常終了

        if state.status == "cancelled":
            return

        # AI CLI の異常終了チェック
        rc = proc.returncode if proc else None
        if rc and rc != 0 and not state.text:
            err_msg = f"AI CLIが異常終了しました (exit code: {rc})"
            if stderr_text:
                # stderr の末尾から有用な情報を抽出
                err_detail = stderr_text[-300:].strip()
                err_msg += f"\n{err_detail}"
            logger.error(
                "AI CLI異常終了 (task=%s, ai_service=%s, rc=%d): %s",
                task_id,
                ai_service,
                rc,
                stderr_text[:500],
            )
            state.status = "error"
            state.error = err_msg
            _persist_task_result(task_id, "error", state.text, state.error)
            await state.queue.put({"type": "error", "message": err_msg})
            await state.queue.put(None)
            return

        state.status = "done"
        _persist_task_result(task_id, "done", state.text, "")
        _persist_llm_usage(task_id, state, client=client_context)
        await state.queue.put(
            {
                "type": "done",
                "web_search_used": state.web_search_used,
                "claude_session_id": state.claude_session_id,
            }
        )
        await state.queue.put(None)

    except Exception as e:
        if state.status == "cancelled":
            return
        logger.error("チーム討議エラー (task=%s): %s", task_id, e, exc_info=True)
        state.status = "error"
        state.error = f"チーム討議中にエラーが発生しました: {type(e).__name__}: {e}"
        _persist_task_result(task_id, "error", state.text, state.error)
        await state.queue.put({"type": "error", "message": state.error})
        await state.queue.put(None)
    finally:
        _concurrent_count -= 1
        _team_semaphore.release()


async def get_task_result(request: Request) -> JSONResponse:
    """バックグラウンドタスクの現在状態を返す（インメモリ → SQLiteフォールバック）"""
    task_id = request.path_params["task_id"]
    state = _active_tasks.get(task_id)
    if state:
        return JSONResponse(
            {
                "status": state.status,
                "text": state.text,
                "error": state.error,
            }
        )
    # インメモリにない場合はSQLiteにフォールバック（再起動後の復帰用）
    persisted = _load_task_result(task_id)
    if persisted:
        return JSONResponse(persisted)
    return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)


async def cancel_task(request: Request) -> JSONResponse:
    """バックグラウンドタスクを中止する"""
    task_id = request.path_params["task_id"]
    state = _active_tasks.get(task_id)
    if not state:
        return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)
    if state.status != "running":
        return JSONResponse({"ok": True, "already": state.status})

    state.status = "cancelled"
    proc = state.proc
    if proc and proc.returncode is None:
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except TimeoutError:
                proc.kill()
        except ProcessLookupError:
            pass

    await state.queue.put({"type": "cancelled"})
    await state.queue.put(None)
    logger.info("タスク中止: task=%s", task_id)
    return JSONResponse({"ok": True})


async def save_web_search(request: Request) -> JSONResponse:
    """Web検索結果をステージングに保存する（フロントエンド用）"""
    try:
        body = await request.json()
        query = body.get("query", "")
        content = body.get("content", "")
        session_id = body.get("session_id", "")
        if not content:
            return JSONResponse({"error": "content は必須です"}, status_code=400)

        from sqlite_store import SQLiteStore

        store = SQLiteStore(_SQLITE_PATH)
        row_id = store.add_web_search_staging(
            query=query,
            content=content[:8000],
            session_id=session_id,
        )
        return JSONResponse({"ok": True, "id": row_id})
    except Exception as e:
        logger.error("Web検索ステージング保存エラー: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)
