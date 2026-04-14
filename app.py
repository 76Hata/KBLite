"""KBLite — KBブラウザの軽量版（ChromaDB/RAG機能なし）"""
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from deps import logger  # noqa: F401

from routes.chat import cancel_task, get_task_result, team_chat
from routes.project import (
    create_project,
    delete_project,
    list_projects,
    move_session,
    rename_project,
)
from routes.session import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    rename_session,
    save_conversation,
    update_conversation,
    update_session_bookmark,
    update_conversation_title,
)
from routes.observability import get_llm_usage_stats, get_observability_stats
from routes.system import get_app_config, get_rate_limits, health, index

_routes = [
    Route("/", index),
    Route("/api/config", get_app_config, methods=["GET"]),
    Route("/health", health),
    Route("/api/rate-limits", get_rate_limits, methods=["GET"]),
    Route("/api/team-chat", team_chat, methods=["POST"]),
    Route("/api/task/{task_id}", get_task_result, methods=["GET"]),
    Route("/api/task/{task_id}/cancel", cancel_task, methods=["POST"]),
    Route("/api/sessions", create_session, methods=["POST"]),
    Route("/api/sessions", list_sessions, methods=["GET"]),
    Route("/api/sessions/{session_id}", get_session, methods=["GET"]),
    Route("/api/sessions/{session_id}", delete_session, methods=["DELETE"]),
    Route("/api/sessions/{session_id}/title", rename_session, methods=["PUT"]),
    Route("/api/sessions/{session_id}/bookmark", update_session_bookmark, methods=["PUT"]),
    Route("/api/conversations", save_conversation, methods=["POST"]),
    Route("/api/conversations/title", update_conversation_title, methods=["PUT"]),
    Route("/api/conversations/{conv_id}", update_conversation, methods=["PUT"]),
    Route("/api/projects", create_project, methods=["POST"]),
    Route("/api/projects", list_projects, methods=["GET"]),
    Route("/api/projects/{project_id}", delete_project, methods=["DELETE"]),
    Route("/api/projects/{project_id}", rename_project, methods=["PUT"]),
    Route("/api/sessions/move", move_session, methods=["PUT"]),
    Route("/api/observability", get_observability_stats, methods=["GET"]),
    Route("/api/llm-usage", get_llm_usage_stats, methods=["GET"]),
    Mount("/static", app=StaticFiles(directory=str(Path(__file__).parent / "static")), name="static"),
]

app = Starlette(routes=_routes)
