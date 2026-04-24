"""セッション・会話CRUDエンドポイント"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from deps import logger, store


async def create_session(request: Request) -> JSONResponse:
    """新規セッション作成"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)
    session_id = str(body.get("session_id", "")).strip()
    title = str(body.get("title", "")).strip()
    first_message = str(body.get("first_message", "")).strip()
    category = str(body.get("category", "")).strip()
    parent_session_id = str(body.get("parent_session_id", "")).strip()
    if not session_id or not title:
        return JSONResponse({"error": "session_id と title は必須です"}, status_code=400)
    try:
        meta = store.create_session(
            session_id, title, first_message, category=category, parent_session_id=parent_session_id
        )
        return JSONResponse({"ok": True, **meta})
    except Exception as e:
        logger.error("セッション作成エラー: %s", e)
        return JSONResponse({"error": "セッション作成に失敗しました"}, status_code=500)


async def list_sessions(request: Request) -> JSONResponse:
    """セッション一覧取得"""
    project_id = request.query_params.get("project_id") or None
    try:
        offset = max(0, int(request.query_params.get("offset", 0)))
        limit = min(200, max(1, int(request.query_params.get("limit", 50))))
    except ValueError:
        offset, limit = 0, 50
    try:
        sessions = store.list_sessions(project_id=project_id, offset=offset, limit=limit)
        total = store.count_sessions(project_id=project_id)
        return JSONResponse({"sessions": sessions, "total": total})
    except Exception as e:
        logger.error("セッション一覧エラー: %s", e)
        return JSONResponse({"sessions": [], "total": 0})


async def get_session(request: Request) -> JSONResponse:
    """セッション詳細（全Q&Aペア）取得"""
    session_id = request.path_params["session_id"]
    try:
        session = store.get_session(session_id)
        if not session:
            return JSONResponse({"error": "セッションが見つかりません"}, status_code=404)
        conversations = store.get_conversations(session_id)
        return JSONResponse({"session": session, "conversations": conversations})
    except Exception as e:
        logger.error("セッション詳細エラー: %s", e)
        return JSONResponse({"error": "セッション取得に失敗しました"}, status_code=500)


async def delete_session(request: Request) -> JSONResponse:
    """セッション削除"""
    session_id = request.path_params["session_id"]
    try:
        store.delete_session(session_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("セッション削除エラー: %s", e)
        return JSONResponse({"error": "セッション削除に失敗しました"}, status_code=500)


async def rename_session(request: Request) -> JSONResponse:
    """セッションタイトル変更"""
    session_id = request.path_params["session_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)
    title = str(body.get("title", "")).strip()
    if not title:
        return JSONResponse({"error": "title は必須です"}, status_code=400)
    try:
        store.update_session(session_id, title=title, touch_updated_at=False)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("セッション名変更エラー: %s", e)
        return JSONResponse({"error": "セッション名変更に失敗しました"}, status_code=500)


async def update_session_bookmark(request: Request) -> JSONResponse:
    """セッションのブックマーク状態を更新"""
    session_id = request.path_params["session_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)

    if "bookmarked" not in body:
        return JSONResponse({"error": "bookmarked は必須です"}, status_code=400)

    try:
        bookmarked = bool(body.get("bookmarked"))
        store.update_session(session_id, bookmarked=bookmarked)
        return JSONResponse({"ok": True, "session_id": session_id, "bookmarked": bookmarked})
    except Exception as e:
        logger.error("ブックマーク更新エラー: %s", e)
        return JSONResponse({"error": "ブックマーク更新に失敗しました"}, status_code=500)


async def save_conversation(request: Request) -> JSONResponse:
    """Q&Aペア保存"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)
    session_id = str(body.get("session_id", "")).strip()
    sequence = body.get("sequence", 0)
    question = str(body.get("question", "")).strip()
    answer = str(body.get("answer", "")).strip()
    title = body.get("title")
    summary = body.get("summary")
    if not session_id or not question or not answer:
        return JSONResponse({"error": "session_id, question, answer は必須です"}, status_code=400)
    try:
        conv_id = store.save_conversation(
            session_id, sequence, question, answer, title=title or "", summary=summary or ""
        )
        store.update_session(session_id, title=title, message_count=sequence + 1)
        return JSONResponse({"ok": True, "id": conv_id})
    except Exception as e:
        logger.error("会話保存エラー: %s", e)
        return JSONResponse({"error": "会話保存に失敗しました"}, status_code=500)


async def update_conversation(request: Request) -> JSONResponse:
    """会話内容（質問・回答）を更新"""
    conv_id = request.path_params["conv_id"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)
    question = body.get("question")
    answer = body.get("answer")
    if question is None and answer is None:
        return JSONResponse({"error": "question または answer のいずれかは必須です"}, status_code=400)
    try:
        store.update_conversation(conv_id, question=question, answer=answer)
        return JSONResponse({"ok": True})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error("会話内容更新エラー: %s", e)
        return JSONResponse({"error": "会話内容の更新に失敗しました"}, status_code=500)


async def update_conversation_title(request: Request) -> JSONResponse:
    """会話タイトル更新"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "不正なリクエストボディです"}, status_code=400)
    conv_id = str(body.get("conv_id", "")).strip()
    title = str(body.get("title", "")).strip()
    if not conv_id or not title:
        return JSONResponse({"error": "conv_id と title は必須です"}, status_code=400)
    try:
        store.update_conversation_title(conv_id, title)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("会話タイトル更新エラー: %s", e)
        return JSONResponse({"error": "会話タイトル更新に失敗しました"}, status_code=500)
