from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.mcp.sse import messages_app as mcp_sse_messages_app
from app.mcp.sse import router as mcp_sse_router


def create_app() -> FastAPI:
    app = FastAPI(title="probe", version="0.1.0")

    app.include_router(health_router)
    app.include_router(mcp_sse_router, prefix="/mcp")
    app.mount("/mcp/messages", mcp_sse_messages_app)

    return app


app = create_app()
