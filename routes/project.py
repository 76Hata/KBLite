"""プロジェクト管理エンドポイント"""

import json
import re
import uuid
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from deps import logger, store

# テンプレートベースパス（インストール後 → 開発時の順でフォールバック）
_KBLITE_ROOT = Path(__file__).parent.parent
_TEMPLATES_BASE = _KBLITE_ROOT / "templates" / "scaffold"
if not _TEMPLATES_BASE.exists():
    _TEMPLATES_BASE = _KBLITE_ROOT / "installer" / "source" / "templates" / "scaffold"

_APP_CONFIG_PATH = _KBLITE_ROOT / "app-config.json"


def _to_kebab(name: str) -> str:
    """プロジェクト名をケバブケースIDに変換する"""
    s = name.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "project"


def _encode_path(root_folder: str) -> str:
    """Windowsパスをメモリフォルダ名用にエンコードする（§13.6）"""
    # C:\ → C--
    s = re.sub(r"^([A-Za-z]):\\", lambda m: m.group(1).upper() + "--", root_folder)
    # バックスラッシュ・スラッシュ → -
    s = s.replace("\\", "-").replace("/", "-")
    # アンダースコア → -
    s = s.replace("_", "-")
    # 連続ハイフンを1つに
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _render_template(tmpl_path: Path, vars: dict[str, str]) -> str:
    text = tmpl_path.read_text(encoding="utf-8")
    for key, val in vars.items():
        text = text.replace("{{" + key + "}}", val)
    return text


async def create_project(request: Request) -> JSONResponse:
    """新規プロジェクト作成"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)
    name = str(body.get("name", "")).strip()
    if not name:
        return JSONResponse({"error": "name は必須です"}, status_code=400)
    project_id = str(uuid.uuid4())
    try:
        meta = store.create_project(project_id, name)
        return JSONResponse({"ok": True, "project_id": project_id, **meta})
    except Exception as e:
        logger.error("プロジェクト作成エラー: %s", e)
        return JSONResponse({"error": "プロジェクト作成に失敗しました"}, status_code=500)


async def list_projects(request: Request) -> JSONResponse:
    """プロジェクト一覧取得"""
    try:
        projects = store.list_projects()
        return JSONResponse({"projects": projects})
    except Exception as e:
        logger.error("プロジェクト一覧エラー: %s", e)
        return JSONResponse({"projects": []})


async def delete_project(request: Request) -> JSONResponse:
    """プロジェクト削除"""
    project_id = request.path_params["project_id"]
    try:
        store.delete_project(project_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("プロジェクト削除エラー: %s", e)
        return JSONResponse({"error": "プロジェクト削除に失敗しました"}, status_code=500)


async def rename_project(request: Request) -> JSONResponse:
    """プロジェクト名変更"""
    project_id = request.path_params["project_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)
    name = str(body.get("name", "")).strip()
    if not name:
        return JSONResponse({"error": "name は必須です"}, status_code=400)
    try:
        store.rename_project(project_id, name)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("プロジェクト名変更エラー: %s", e)
        return JSONResponse({"error": "プロジェクト名変更に失敗しました"}, status_code=500)


async def scaffold_workspace_project(request: Request) -> JSONResponse:
    """新規プロジェクト向けCLAUDE.md/.claude/設定を自動生成し、app-config.jsonを更新する"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    name = str(body.get("name", "")).strip()
    root_folder = str(body.get("root_folder", "")).strip()
    language = str(body.get("language", "blank")).strip() or "blank"

    if not name:
        return JSONResponse({"error": "name は必須です"}, status_code=400)
    if not root_folder:
        return JSONResponse({"error": "root_folder は必須です"}, status_code=400)

    root = Path(root_folder)
    if not root.exists():
        return JSONResponse({"error": "folder_not_found", "detail": str(root)}, status_code=400)

    kblite_install_dir = str(_KBLITE_ROOT).replace("\\", "/")
    encoded_path = _encode_path(root_folder)
    tmpl_vars = {
        "PROJECT_NAME": name,
        "ROOT_FOLDER": root_folder,
        "ROOT_FOLDER_ENCODED": encoded_path,
        "KBLITE_INSTALL_DIR": kblite_install_dir,
    }

    try:
        # L0: CLAUDE.md
        claude_md = _render_template(_TEMPLATES_BASE / "L0" / "CLAUDE.md.tmpl", tmpl_vars)
        (root / "CLAUDE.md").write_text(claude_md, encoding="utf-8")

        # L0: .claude/settings.local.json
        claude_dir = root / ".claude"
        claude_dir.mkdir(exist_ok=True)
        settings_json = _render_template(_TEMPLATES_BASE / "L0" / "settings.local.json.tmpl", tmpl_vars)
        (claude_dir / "settings.local.json").write_text(settings_json, encoding="utf-8")

        # L0: .claude/rules/ (空フォルダ)
        rules_dir = claude_dir / "rules"
        rules_dir.mkdir(exist_ok=True)

        # L1: 言語別追加ファイル
        l1_dir = _TEMPLATES_BASE / "L1" / language
        if language != "blank" and l1_dir.exists():
            for tmpl_file in l1_dir.rglob("*.tmpl"):
                rel = tmpl_file.relative_to(l1_dir)
                dest = claude_dir / rel.with_suffix("")  # .tmpl を除去
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(_render_template(tmpl_file, tmpl_vars), encoding="utf-8")

        # メモリフォルダ生成
        memory_dir = Path.home() / ".claude" / "projects" / encoded_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        # app-config.json 更新
        project_id = _to_kebab(name)
        config = json.loads(_APP_CONFIG_PATH.read_text(encoding="utf-8"))
        projects: list[dict] = config.setdefault("workspace_projects", [])
        # 同一IDが既にあれば上書き
        projects = [p for p in projects if p.get("id") != project_id]
        projects.append(
            {
                "id": project_id,
                "label": name,
                "cwd": root_folder,
                "default_team": "general",
                "default_category": "general",
            }
        )
        config["workspace_projects"] = projects
        _APP_CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    except Exception as e:
        logger.error("scaffold エラー: %s", e)
        return JSONResponse({"error": "scaffold_failed", "detail": str(e)}, status_code=500)

    return JSONResponse({"ok": True, "path": str(root), "id": project_id})


async def analyze_workspace_project(request: Request) -> JSONResponse:
    """既存フォルダのマニフェストを検出して言語・FWを推定する"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    root_folder = str(body.get("root_folder", "")).strip()
    if not root_folder:
        return JSONResponse({"error": "root_folder は必須です"}, status_code=400)

    root = Path(root_folder)
    if not root.exists():
        return JSONResponse({"error": "folder_not_found", "detail": str(root)}, status_code=400)

    detected_files: list[str] = []
    language = "unknown"
    framework = ""

    # 設計書§13.5の検出ルール（優先順）
    pkg_json = root / "package.json"
    if pkg_json.exists():
        detected_files.append("package.json")
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8-sig"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "react" in deps or "react-dom" in deps:
                language = "react"
                framework = "Next.js" if "next" in deps else "React"
            else:
                language = "javascript"
                framework = "Node.js"
        except Exception:
            language = "javascript"
    elif (root / "composer.json").exists():
        detected_files.append("composer.json")
        language = "php"
        try:
            composer = json.loads((root / "composer.json").read_text(encoding="utf-8-sig"))
            require = composer.get("require", {})
            if "laravel/framework" in require:
                framework = "Laravel"
            elif "symfony/symfony" in require or any("symfony/" in k for k in require):
                framework = "Symfony"
        except Exception:
            pass
    elif (
        (root / "pyproject.toml").exists()
        or (root / "setup.py").exists()
        or (root / "requirements.txt").exists()
    ):
        for fname in ("pyproject.toml", "setup.py", "requirements.txt"):
            if (root / fname).exists():
                detected_files.append(fname)
        language = "python"
    elif (root / "go.mod").exists():
        detected_files.append("go.mod")
        language = "go"
    elif (root / "Cargo.toml").exists():
        detected_files.append("Cargo.toml")
        language = "rust"

    return JSONResponse({"language": language, "framework": framework, "files": detected_files})


async def move_session(request: Request) -> JSONResponse:
    """セッションをプロジェクトに移動"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)
    session_id = str(body.get("session_id", "")).strip()
    project_id = str(body.get("project_id", "")).strip()  # 空文字 = 未分類に戻す
    if not session_id:
        return JSONResponse({"error": "session_id は必須です"}, status_code=400)
    try:
        store.move_session_to_project(session_id, project_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("セッション移動エラー: %s", e)
        return JSONResponse({"error": "セッション移動に失敗しました"}, status_code=500)
