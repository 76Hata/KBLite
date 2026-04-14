"""プロジェクト管理エンドポイント"""
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse

from deps import logger, store


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
