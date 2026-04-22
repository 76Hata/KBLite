"""システム系エンドポイント — ヘルスチェック・設定・Rate Limits"""

import asyncio
import json
import os
import re as _re
import shutil
import subprocess
import sys
from pathlib import Path

_AUTH_CONFIG_PATH = Path(__file__).parent.parent / "data" / "auth.json"

# ── claude login OAuth フロー 状態管理 ─────────────────────────
_claude_login: dict = {
    "proc": None,  # asyncio.subprocess.Process | None
    "url": None,  # str | None — 認証URL
    "status": "idle",  # "idle" | "starting" | "pending" | "done" | "failed"
}

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from deps import (
    _INDEX_HTML_PATH,
    AI_SERVICES,
    CATEGORIES,
    MODELS,
    TEAMS,
    WORKSPACE_PROJECTS,
    resolve_project_cwd,
    store,
)


def _workspace_projects_with_resolved_cwd() -> list[dict]:
    enriched: list[dict] = []
    for p in WORKSPACE_PROJECTS:
        entry = dict(p)
        pid = str(p.get("id") or "")
        entry["resolved_cwd_claude"] = resolve_project_cwd(pid, "claude")
        entry["resolved_cwd_cursor"] = resolve_project_cwd(pid, "cursor")
        enriched.append(entry)
    return enriched


_RATE_LIMITS_PATH = (
    Path(os.getenv("SQLITE_PATH", str(Path(__file__).parent.parent / "data" / "sqlite" / "kblite.db"))).parent
    / "rate-limits.json"
)


async def index(request: Request) -> HTMLResponse:
    return HTMLResponse(_INDEX_HTML_PATH.read_text(encoding="utf-8"))


async def get_app_config(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "categories": CATEGORIES,
            "teams": TEAMS,
            "models": MODELS,
            "ai_services": AI_SERVICES,
            "workspace_projects": _workspace_projects_with_resolved_cwd(),
        }
    )


async def get_rate_limits(request: Request) -> JSONResponse:
    if not _RATE_LIMITS_PATH.is_file():
        return JSONResponse({"error": "not_available"}, status_code=404)
    try:
        data = json.loads(_RATE_LIMITS_PATH.read_text(encoding="utf-8"))
        return JSONResponse(data)
    except (json.JSONDecodeError, OSError):
        return JSONResponse({"error": "read_error"}, status_code=500)


async def health(request: Request) -> JSONResponse:
    sqlite_ok = store.sqlite_healthcheck()
    return JSONResponse(
        {"status": "ok" if sqlite_ok else "degraded", "sqlite": "ok" if sqlite_ok else "error"},
        status_code=200 if sqlite_ok else 503,
    )


async def restart_server(request: Request) -> JSONResponse:
    """サーバーを自己再起動する（デタッチしたバッチプロセス経由）"""
    app_dir = Path(__file__).parent.parent
    bat_path = app_dir / "restart.bat"
    port = 8080

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        ["cmd", "/c", str(bat_path)],
        cwd=str(app_dir),
        close_fds=True,
        creationflags=creationflags,
    )

    return JSONResponse({"status": "restarting", "port": port})


def _is_subpath(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


async def open_file(request: Request) -> JSONResponse:
    """指定パスのファイルを OS 既定の関連付けアプリで開く。

    許可ルート: プロジェクトルート配下 および ~/.claude/ 配下のみ。
    それ以外は 403 を返す。
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    raw_path = str(data.get("path") or "").strip()
    if not raw_path:
        return JSONResponse({"error": "path_required"}, status_code=400)

    try:
        target = Path(raw_path).expanduser().resolve(strict=False)
    except Exception as e:
        return JSONResponse({"error": "invalid_path", "detail": str(e)}, status_code=400)

    project_root = Path(__file__).parent.parent.resolve()
    home_claude = (Path.home() / ".claude").resolve()
    allowed_roots = [project_root, home_claude]

    if not any(_is_subpath(target, root) for root in allowed_roots):
        return JSONResponse(
            {
                "error": "forbidden_path",
                "detail": "Only project root and ~/.claude are allowed",
                "path": str(target),
            },
            status_code=403,
        )

    if not target.exists():
        return JSONResponse({"error": "not_found", "path": str(target)}, status_code=404)

    # プラットフォーム別に既定アプリでファイルを開く。
    # Windows では VS Code (code --reuse-window) を最優先してウィンドウを最前面に移動し、
    # VS Code がない場合は os.startfile → explorer.exe の順でフォールバックする。
    opened_via = None
    last_error: str | None = None
    try:
        if sys.platform == "win32":
            code_exe = shutil.which("code")
            if code_exe:
                # --reuse-window: 既存 VS Code ウィンドウを再利用してフォーカスを移す
                subprocess.Popen(
                    [code_exe, "--reuse-window", str(target)],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                opened_via = "vscode"
                # VS Code をアクティブ化（メインウィンドウを持つプロセスに絞って AppActivate）
                ps_script = (
                    "Start-Sleep -Milliseconds 800;"
                    "$wsh = New-Object -ComObject WScript.Shell;"
                    "$proc = Get-Process -Name 'Code' -ErrorAction SilentlyContinue"
                    " | Where-Object { $_.MainWindowHandle -ne 0 }"
                    " | Select-Object -First 1;"
                    "if ($proc) { $wsh.AppActivate($proc.Id) | Out-Null }"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                try:
                    os.startfile(str(target))  # type: ignore[attr-defined]
                    opened_via = "os.startfile"
                except OSError as e:
                    last_error = f"os.startfile failed: {e}"
                    subprocess.Popen(
                        ["explorer.exe", str(target)],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    opened_via = "explorer.exe"
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
            opened_via = "open"
        else:
            subprocess.Popen(["xdg-open", str(target)])
            opened_via = "xdg-open"
    except Exception as e:
        detail = f"{last_error + '; ' if last_error else ''}{e}"
        print(f"[open_file] FAILED path={target} detail={detail}", file=sys.stderr)
        return JSONResponse({"error": "open_failed", "detail": detail}, status_code=500)

    print(f"[open_file] OK via={opened_via} path={target}", file=sys.stderr)
    return JSONResponse({"status": "ok", "path": str(target), "via": opened_via})


async def get_auth_status(request: Request) -> JSONResponse:
    """現在の認証状態を返す（APIキーが設定されているかどうか）"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    has_key = bool(api_key)
    prefix = (api_key[:8] + "...") if has_key else ""
    return JSONResponse({"has_api_key": has_key, "key_prefix": prefix})


async def set_auth_key(request: Request) -> JSONResponse:
    """APIキーを設定し、data/auth.json に永続化する"""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        return JSONResponse({"error": "api_key_required"}, status_code=400)
    if not api_key.startswith("sk-ant-"):
        return JSONResponse(
            {"error": "invalid_api_key_format", "detail": "Anthropic APIキーは sk-ant- で始まります"},
            status_code=400,
        )

    # 環境変数に即時反映（現プロセス）
    os.environ["ANTHROPIC_API_KEY"] = api_key

    # data/auth.json に永続化
    try:
        _AUTH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _AUTH_CONFIG_PATH.write_text(
            json.dumps({"ANTHROPIC_API_KEY": api_key}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        return JSONResponse({"error": "save_failed", "detail": str(e)}, status_code=500)

    return JSONResponse({"status": "ok", "key_prefix": api_key[:8] + "..."})


async def clear_auth_key(request: Request) -> JSONResponse:
    """APIキーを削除する"""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        if _AUTH_CONFIG_PATH.is_file():
            _AUTH_CONFIG_PATH.unlink()
    except Exception as e:
        return JSONResponse({"error": "delete_failed", "detail": str(e)}, status_code=500)
    return JSONResponse({"status": "ok"})


async def debug_env(request: Request) -> JSONResponse:
    """デバッグ用: Claude CLI パス・イベントループ・環境情報を返す"""
    claude_path = shutil.which("claude")
    loop = asyncio.get_event_loop()
    return JSONResponse(
        {
            "platform": sys.platform,
            "python_version": sys.version,
            "event_loop_type": type(loop).__name__,
            "claude_which": claude_path,
            "PATH": os.environ.get("PATH", ""),
            "sqlite_ok": store.sqlite_healthcheck(),
        }
    )


# ── claude login OAuth フロー ──────────────────────────────────


async def _collect_login_output(proc: asyncio.subprocess.Process) -> None:
    """バックグラウンドで stdout/stderr を読み込み、認証URLと完了状態を更新する"""
    try:

        async def read_stream(stream: asyncio.StreamReader | None) -> None:
            if stream is None:
                return
            async for raw in stream:
                line = raw.decode(errors="replace").strip()
                if not _claude_login["url"]:
                    m = _re.search(r"https://[^\s<>\"']+", line)
                    if m:
                        _claude_login["url"] = m.group(0)
                        _claude_login["status"] = "pending"

        await asyncio.gather(
            read_stream(proc.stdout),
            read_stream(proc.stderr),
            return_exceptions=True,
        )
        ret = await proc.wait()
        _claude_login["status"] = "done" if ret == 0 else "failed"
    except Exception:
        _claude_login["status"] = "failed"


async def start_claude_login(request: Request) -> JSONResponse:
    """claude login を起動して認証URLを取得する（OAuth フロー開始）"""
    # 既存プロセスを終了
    old_proc = _claude_login.get("proc")
    if old_proc is not None and old_proc.returncode is None:
        try:
            old_proc.terminate()
        except Exception:
            pass

    _claude_login["proc"] = None
    _claude_login["url"] = None
    _claude_login["status"] = "starting"

    claude_path = shutil.which("claude")
    if not claude_path:
        _claude_login["status"] = "failed"
        return JSONResponse(
            {"error": "claude_not_found", "detail": "Claude CLI が PATH に見つかりません"},
            status_code=500,
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            claude_path,
            "auth",
            "login",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        _claude_login["proc"] = proc

        # バックグラウンドでURL収集タスクを起動
        asyncio.get_event_loop().create_task(_collect_login_output(proc))

        # URL が届くまで最大10秒待つ
        for _ in range(20):
            await asyncio.sleep(0.5)
            if _claude_login["url"] or _claude_login["status"] == "failed":
                break

        if _claude_login["url"]:
            return JSONResponse({"status": "pending", "url": _claude_login["url"]})
        elif _claude_login["status"] == "failed":
            return JSONResponse(
                {"error": "login_failed", "detail": "claude login の起動に失敗しました"},
                status_code=500,
            )
        else:
            # タイムアウト: URLはまだ取得できていないが処理は継続
            return JSONResponse({"status": "starting", "url": None})

    except Exception as e:
        _claude_login["status"] = "failed"
        return JSONResponse({"error": "start_failed", "detail": str(e)}, status_code=500)


async def get_claude_login_status(request: Request) -> JSONResponse:
    """claude login の進捗状態とURLを返す"""
    status = _claude_login["status"]
    url = _claude_login["url"]
    proc = _claude_login.get("proc")

    # プロセス終了チェック（バックグラウンドタスクが間に合っていない場合の補完）
    if proc is not None and proc.returncode is not None and status == "pending":
        _claude_login["status"] = "done" if proc.returncode == 0 else "failed"
        status = _claude_login["status"]

    return JSONResponse({"status": status, "url": url})


async def cancel_claude_login(request: Request) -> JSONResponse:
    """実行中の claude login をキャンセルする"""
    proc = _claude_login.get("proc")
    if proc is not None and proc.returncode is None:
        try:
            proc.terminate()
        except Exception:
            pass
    _claude_login["proc"] = None
    _claude_login["url"] = None
    _claude_login["status"] = "idle"
    return JSONResponse({"status": "cancelled"})


async def get_claude_auth_info(request: Request) -> JSONResponse:
    """claude auth status を実行してログイン状態を返す"""
    claude_path = shutil.which("claude")
    if not claude_path:
        return JSONResponse({"error": "claude_not_found"}, status_code=500)
    try:
        result = await asyncio.create_subprocess_exec(
            claude_path,
            "auth",
            "status",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=10.0)
        text = stdout.decode(errors="replace").strip() or stderr.decode(errors="replace").strip()
        try:
            return JSONResponse(json.loads(text))
        except Exception:
            return JSONResponse({"raw": text})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
