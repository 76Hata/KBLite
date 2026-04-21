"""タスク管理 API エンドポイント（ルーター層）

HTTP 変換のみを担い、業務ロジックは TaskService に委譲する。
TaskValidationError / TaskNotFoundError をそれぞれ 400 / 404 に翻訳する。
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from deps import logger, store
from models.task import TaskNotFoundError, TaskValidationError
from services.task_service import TaskService

_service = TaskService(store)


async def _read_json(request: Request) -> dict:
    """リクエストボディを JSON として読み込み、辞書でなければ TaskValidationError を送出する。"""
    try:
        body = await request.json()
    except Exception as e:
        raise TaskValidationError("不正なリクエストボディです") from e
    if not isinstance(body, dict):
        raise TaskValidationError("不正なリクエストボディです")
    return body


async def list_tasks(request: Request) -> JSONResponse:
    """タスク一覧取得（status / session_id / scope / source でフィルタ可）"""
    try:
        tasks = _service.list_tasks(
            status=request.query_params.get("status") or None,
            session_id=request.query_params.get("session_id") or None,
            scope=request.query_params.get("scope") or None,
            source=request.query_params.get("source") or None,
        )
        return JSONResponse({"tasks": tasks})
    except Exception as e:
        logger.error("タスク一覧取得エラー: %s", e)
        return JSONResponse({"tasks": []})


async def create_task(request: Request) -> JSONResponse:
    """タスク作成"""
    try:
        body = await _read_json(request)
        task = _service.create_task(body)
        return JSONResponse({"ok": True, "task": task}, status_code=201)
    except TaskValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.error("タスク作成エラー: %s", e)
        return JSONResponse({"error": "タスク作成に失敗しました"}, status_code=500)


async def get_task(request: Request) -> JSONResponse:
    """タスク取得"""
    task_id = request.path_params["task_id"]
    try:
        task = _service.get_task(task_id)
        return JSONResponse({"task": task})
    except TaskNotFoundError:
        return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)


async def update_task(request: Request) -> JSONResponse:
    """タスク更新（title / description / status / priority / due_date / session_id / scope）"""
    task_id = request.path_params["task_id"]
    try:
        body = await _read_json(request)
        task = _service.update_task(task_id, body)
        return JSONResponse({"ok": True, "task": task})
    except TaskValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except TaskNotFoundError:
        return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)
    except Exception as e:
        logger.error("タスク更新エラー: %s", e)
        return JSONResponse({"error": "タスク更新に失敗しました"}, status_code=500)


async def delete_task(request: Request) -> JSONResponse:
    """タスク削除"""
    task_id = request.path_params["task_id"]
    try:
        _service.delete_task(task_id)
        return JSONResponse({"ok": True})
    except TaskNotFoundError:
        return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)
    except Exception as e:
        logger.error("タスク削除エラー: %s", e)
        return JSONResponse({"error": "タスク削除に失敗しました"}, status_code=500)


async def add_task_note(request: Request) -> JSONResponse:
    """タスクにノートを追加"""
    task_id = request.path_params["task_id"]
    try:
        body = await _read_json(request)
        note_obj = _service.add_task_note(task_id, body)
        return JSONResponse({"ok": True, "note": note_obj}, status_code=201)
    except TaskValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except TaskNotFoundError:
        return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)
    except Exception as e:
        logger.error("ノート追加エラー: %s", e)
        return JSONResponse({"error": "ノート追加に失敗しました"}, status_code=500)
