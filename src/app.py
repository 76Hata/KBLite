"""KBLite Browser UI - FastAPI Webアプリ"""

import os
import sys

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import KBLiteDB

app = FastAPI(title="KBLite Browser")

# パス設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


def get_db() -> KBLiteDB:
    return KBLiteDB()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    db = get_db()
    try:
        stats = db.get_stats()
        recent = db.list_sessions(limit=5)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "stats": stats,
                "recent_sessions": recent["sessions"],
            },
        )
    finally:
        db.close()


@app.get("/sessions", response_class=HTMLResponse)
async def sessions(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    db = get_db()
    try:
        result = db.list_sessions(limit=limit, offset=offset)
        return templates.TemplateResponse(
            request=request,
            name="sessions.html",
            context={
                "sessions": result["sessions"],
                "total": result["total"],
                "limit": limit,
                "offset": offset,
            },
        )
    finally:
        db.close()


@app.get("/session/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, session_id: str):
    db = get_db()
    try:
        session = db.get_session(session_id)
        if session is None:
            return templates.TemplateResponse(
                request=request,
                name="session_detail.html",
                context={"session": None, "conversations": []},
                status_code=404,
            )
        conversations = db.get_conversations_by_session(session_id)
        return templates.TemplateResponse(
            request=request,
            name="session_detail.html",
            context={"session": session, "conversations": conversations},
        )
    finally:
        db.close()


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query("", min_length=0)):
    db = get_db()
    try:
        conv_results = []
        mem_results = []
        if q:
            conv_results = db.search_conversations(q)["results"]
            mem_results = db.search_memories(q)["results"]
        return templates.TemplateResponse(
            request=request,
            name="search.html",
            context={
                "query": q,
                "conv_results": conv_results,
                "mem_results": mem_results,
            },
        )
    finally:
        db.close()


@app.get("/memories", response_class=HTMLResponse)
async def memories(
    request: Request,
    q: str = Query("", min_length=0),
    category: str = Query("", min_length=0),
):
    db = get_db()
    try:
        if q:
            result = db.search_memories(q, category=category or None)
            memos = result["results"]
        else:
            cur = db._conn.cursor()
            if category:
                rows = cur.execute(
                    """SELECT m.id, m.title, m.content, m.category, m.created_at, m.updated_at
                       FROM memories m WHERE m.category = ? ORDER BY m.updated_at DESC""",
                    (category,),
                ).fetchall()
            else:
                rows = cur.execute(
                    """SELECT m.id, m.title, m.content, m.category, m.created_at, m.updated_at
                       FROM memories m ORDER BY m.updated_at DESC"""
                ).fetchall()
            memos = []
            for r in rows:
                d = dict(r)
                tags = cur.execute(
                    "SELECT tag FROM memory_tags WHERE memory_id = ?", (d["id"],)
                ).fetchall()
                d["tags"] = [t["tag"] for t in tags]
                memos.append(d)
        return templates.TemplateResponse(
            request=request,
            name="memories.html",
            context={"memories": memos, "query": q, "category": category},
        )
    finally:
        db.close()


@app.get("/memory/{memory_id}", response_class=HTMLResponse)
async def memory_detail(request: Request, memory_id: int):
    db = get_db()
    try:
        memory = db.get_memory(memory_id)
        return templates.TemplateResponse(
            request=request,
            name="memories.html",
            context={
                "memory_detail": memory,
                "memories": [],
                "query": "",
                "category": "",
            },
        )
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8780, reload=True)
