"""KBLite — KBブラウザの軽量版（ChromaDBの代わりにSQLite+FTS5でRAGを実装）"""

import sys

# Windows で asyncio.create_subprocess_exec を使うには ProactorEventLoop が必要。
# uvicorn は SelectorEventLoop を使う場合があるため、起動前に明示的に設定する。
if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from deps import logger  # noqa: F401
from routes.chat import cancel_task, get_task_result, team_chat
from routes.permission import (
    add_permission,
    approve_permission_request,
    deny_permission_request,
    get_permissions,
    list_permission_requests,
    remove_permission,
    submit_permission_request,
)
from routes.project import (
    analyze_workspace_project,
    create_project,
    delete_project,
    list_projects,
    move_session,
    rename_project,
    scaffold_workspace_project,
)
from routes.search import rebuild_index, search_conversations, search_stats
from routes.session import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    rename_session,
    save_conversation,
    update_conversation,
    update_conversation_title,
    update_session_bookmark,
)
from routes.system import (
    cancel_claude_login,
    clear_auth_key,
    debug_env,
    get_app_config,
    get_auth_status,
    get_claude_auth_info,
    get_claude_login_status,
    get_rate_limits,
    health,
    index,
    open_file,
    pick_folder,
    restart_server,
    set_auth_key,
    start_claude_login,
    test_auth_error,
    write_skill_file,
)
from routes.task import (
    add_task_note,
    create_task,
    delete_task,
    get_task,
    list_tasks,
    update_task,
)

_routes = [
    Route("/", index),
    Route("/api/config", get_app_config, methods=["GET"]),
    Route("/health", health),
    Route("/api/rate-limits", get_rate_limits, methods=["GET"]),
    Route("/api/auth/status", get_auth_status, methods=["GET"]),
    Route("/api/auth/set-key", set_auth_key, methods=["POST"]),
    Route("/api/auth/clear", clear_auth_key, methods=["DELETE"]),
    Route("/api/auth/claude-login/start", start_claude_login, methods=["POST"]),
    Route("/api/auth/claude-login/status", get_claude_login_status, methods=["GET"]),
    Route("/api/auth/claude-login/cancel", cancel_claude_login, methods=["DELETE"]),
    Route("/api/auth/claude-auth-info", get_claude_auth_info, methods=["GET"]),
    Route("/api/debug-env", debug_env, methods=["GET"]),
    Route("/api/test/auth-error", test_auth_error, methods=["GET"]),
    Route("/api/restart", restart_server, methods=["POST"]),
    Route("/api/open_file", open_file, methods=["POST"]),
    Route("/api/system/pick-folder", pick_folder, methods=["POST"]),
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
    Route("/api/workspace-projects/scaffold", scaffold_workspace_project, methods=["POST"]),
    Route("/api/workspace-projects/analyze", analyze_workspace_project, methods=["POST"]),
    Route("/api/sessions/move", move_session, methods=["PUT"]),
    Route("/api/search", search_conversations, methods=["GET"]),
    Route("/api/search/stats", search_stats, methods=["GET"]),
    Route("/api/search/rebuild", rebuild_index, methods=["POST"]),
    Route("/api/tasks", list_tasks, methods=["GET"]),
    Route("/api/tasks", create_task, methods=["POST"]),
    Route("/api/tasks/{task_id}", get_task, methods=["GET"]),
    Route("/api/tasks/{task_id}", update_task, methods=["PUT"]),
    Route("/api/tasks/{task_id}", delete_task, methods=["DELETE"]),
    Route("/api/tasks/{task_id}/notes", add_task_note, methods=["POST"]),
    Route("/api/permissions", get_permissions, methods=["GET"]),
    Route("/api/permissions/allow", add_permission, methods=["POST"]),
    Route("/api/permissions/allow", remove_permission, methods=["DELETE"]),
    Route("/api/permissions/requests", list_permission_requests, methods=["GET"]),
    Route("/api/permissions/requests", submit_permission_request, methods=["POST"]),
    Route("/api/permissions/requests/{request_id}/approve", approve_permission_request, methods=["POST"]),
    Route("/api/permissions/requests/{request_id}/deny", deny_permission_request, methods=["POST"]),
    Route("/api/internal/write_skill_file", write_skill_file, methods=["POST"]),
    Mount("/static", app=StaticFiles(directory=str(Path(__file__).parent / "static")), name="static"),  # noqa: E501
]

app = Starlette(routes=_routes)
