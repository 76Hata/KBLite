"""タスク管理 API エンドポイント"""
from starlette.requests import Request
from starlette.responses import JSONResponse

from deps import logger, store


async def list_tasks(request: Request) -> JSONResponse:
    """タスク一覧取得（status / session_id でフィルタ可）"""
    status = request.query_params.get("status") or None
    session_id = request.query_params.get("session_id") or None
    try:
        tasks = store.list_tasks(status=status, session_id=session_id)
        return JSONResponse({"tasks": tasks})
    except Exception as e:
        logger.error("タスク一覧取得エラー: %s", e)
        return JSONResponse({"tasks": []})


async def create_task(request: Request) -> JSONResponse:
    """タスク作成"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)

    title = str(body.get("title", "")).strip()
    if not title:
        return JSONResponse({"error": "title は必須です"}, status_code=400)

    description = str(body.get("description", "")).strip()
    priority = str(body.get("priority", "normal")).strip()
    session_id = body.get("session_id") or None
    due_date = body.get("due_date") or None

    if priority not in ("low", "normal", "high"):
        priority = "normal"

    try:
        task = store.create_task(
            title=title,
            description=description,
            priority=priority,
            session_id=session_id,
            due_date=due_date,
        )
        return JSONResponse({"ok": True, "task": task}, status_code=201)
    except Exception as e:
        logger.error("タスク作成エラー: %s", e)
        return JSONResponse({"error": "タスク作成に失敗しました"}, status_code=500)


async def get_task(request: Request) -> JSONResponse:
    """タスク取得"""
    task_id = request.path_params["task_id"]
    task = store.get_task(task_id)
    if task is None:
        return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)
    task["notes"] = store._list_notes_for(task_id)
    return JSONResponse({"task": task})


async def update_task(request: Request) -> JSONResponse:
    """タスク更新（title / description / status / priority / due_date）"""
    task_id = request.path_params["task_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)

    allowed_fields = {"title", "description", "status", "priority",
                      "session_id", "due_date"}
    updates = {k: v for k, v in body.items() if k in allowed_fields}

    if "status" in updates and updates["status"] not in ("todo", "in_progress", "done", "cancelled"):
        return JSONResponse({"error": "status は todo/in_progress/done/cancelled のいずれかです"}, status_code=400)

    try:
        task = store.update_task(task_id, **updates)
        if task is None:
            return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)
        task["notes"] = store._list_notes_for(task_id)
        return JSONResponse({"ok": True, "task": task})
    except Exception as e:
        logger.error("タスク更新エラー: %s", e)
        return JSONResponse({"error": "タスク更新に失敗しました"}, status_code=500)


async def delete_task(request: Request) -> JSONResponse:
    """タスク削除"""
    task_id = request.path_params["task_id"]
    try:
        deleted = store.delete_task(task_id)
        if not deleted:
            return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("タスク削除エラー: %s", e)
        return JSONResponse({"error": "タスク削除に失敗しました"}, status_code=500)


async def add_task_note(request: Request) -> JSONResponse:
    """タスクにノートを追加"""
    task_id = request.path_params["task_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)

    note = str(body.get("note", "")).strip()
    if not note:
        return JSONResponse({"error": "note は必須です"}, status_code=400)

    if store.get_task(task_id) is None:
        return JSONResponse({"error": "タスクが見つかりません"}, status_code=404)

    try:
        note_obj = store.add_task_note(task_id, note)
        return JSONResponse({"ok": True, "note": note_obj}, status_code=201)
    except Exception as e:
        logger.error("ノート追加エラー: %s", e)
        return JSONResponse({"error": "ノート追加に失敗しました"}, status_code=500)
