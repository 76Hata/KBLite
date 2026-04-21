"""FTS5 全文検索エンドポイント"""
from starlette.requests import Request
from starlette.responses import JSONResponse

from deps import logger, store


async def search_conversations(request: Request) -> JSONResponse:
    """GET /api/search?q=キーワード&limit=5"""
    query = request.query_params.get("q", "").strip()
    if not query:
        return JSONResponse({"results": [], "query": "", "total": 0})

    limit = min(int(request.query_params.get("limit", "10")), 50)

    results = store.fts_search(query, limit=limit)
    return JSONResponse({
        "results": results,
        "query": query,
        "total": len(results),
    })


async def search_stats(request: Request) -> JSONResponse:
    """GET /api/search/stats — FTS5 インデックス統計"""
    stats = store.fts_stats()
    return JSONResponse(stats)


async def rebuild_index(request: Request) -> JSONResponse:
    """POST /api/search/rebuild — FTS5 インデックス再構築"""
    try:
        count = store.rebuild_fts_index()
        return JSONResponse({"status": "ok", "indexed": count})
    except Exception as e:
        logger.error("FTS5 再構築エラー: %s", e)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
