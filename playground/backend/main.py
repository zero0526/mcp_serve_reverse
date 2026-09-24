"""Main entrypoint cho Playground Backend Server (Starlette ASGI)."""

import os
import sys
import asyncio
from contextlib import asynccontextmanager

if sys.platform == "win32":
    # On Windows, Playwright requires ProactorEventLoop to spawn browser subprocesses
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from playground.backend.api.routes_tasks import (
    create_task_endpoint,
    get_task_endpoint,
    list_tasks_endpoint,
    update_task_status_endpoint,
)
from playground.backend.api.routes_sessions import (
    close_session_endpoint,
    get_session_status_endpoint,
    launch_session_endpoint,
    list_sessions_endpoint,
)
from playground.backend.api.routes_graph import (
    delete_node_endpoint,
    get_graph_endpoint,
    update_node_alias_endpoint,
)
from playground.backend.api.routes_evolution import (
    get_evolution_summary_endpoint,
    get_session_logs_endpoint,
)
from playground.backend.config import settings
from playground.backend.dependencies import get_container


async def health_check_endpoint(request) -> JSONResponse:
    """GET /api/health: Kiểm tra tình trạng backend server."""
    return JSONResponse({
        "status": "healthy",
        "service": "mcp-reverse-studio-api",
        "version": "1.0.0",
    })


@asynccontextmanager
async def lifespan(app: Starlette):
    """Khởi tạo container và database schema khi server khởi động."""
    container = await get_container()
    await container.initialize()
    yield
    # Cleanup khi shutdown nếu có active browsers
    for browser in list(container.start_session_uc.active_browsers.values()):
        try:
            await browser.stop()
        except Exception:
            pass


routes = [
    # Health check
    Route("/api/health", health_check_endpoint, methods=["GET"]),

    # Task APIs
    Route("/api/tasks", create_task_endpoint, methods=["POST"]),
    Route("/api/tasks", list_tasks_endpoint, methods=["GET"]),
    Route("/api/tasks/{task_id}", get_task_endpoint, methods=["GET"]),
    Route("/api/tasks/{task_id}/status", update_task_status_endpoint, methods=["PATCH"]),

    # Session APIs
    Route("/api/sessions", list_sessions_endpoint, methods=["GET"]),
    Route("/api/sessions/{session_id}/launch", launch_session_endpoint, methods=["POST"]),
    Route("/api/sessions/{session_id}/close", close_session_endpoint, methods=["POST"]),
    Route("/api/sessions/{session_id}/status", get_session_status_endpoint, methods=["GET"]),

    # Graph Studio APIs
    Route("/api/graph/{session_id}", get_graph_endpoint, methods=["GET"]),
    Route("/api/graph/{session_id}/nodes/{node_id}/alias", update_node_alias_endpoint, methods=["PATCH"]),
    Route("/api/graph/{session_id}/nodes/{node_id}", delete_node_endpoint, methods=["DELETE"]),

    # Evolution & Retrospective APIs
    Route("/api/evolution/summary", get_evolution_summary_endpoint, methods=["GET"]),
    Route("/api/evolution/logs/{task_id}", get_session_logs_endpoint, methods=["GET"]),
]

# Nếu đã build frontend (dist folder), mount static files để phục vụ trực tiếp
dist_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
)
if os.path.isdir(dist_dir):
    routes.append(
        Mount("/", app=StaticFiles(directory=dist_dir, html=True), name="frontend_dist")
    )

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(
    debug=settings.debug,
    routes=routes,
    middleware=middleware,
    lifespan=lifespan,
)


def start():
    """Chạy server thông qua Uvicorn."""
    import sys
    import uvicorn

    # Trên Windows, Uvicorn reload=True mặc định chọn SelectorEventLoop (không hỗ trợ subprocess cho Playwright).
    # Ta chỉ định ProactorEventLoop để Playwright / Chromium khởi chạy mượt mà.
    loop_factory = "asyncio.windows_events:ProactorEventLoop" if sys.platform == "win32" else "auto"

    uvicorn.run(
        "playground.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        loop=loop_factory,
    )


if __name__ == "__main__":
    start()
