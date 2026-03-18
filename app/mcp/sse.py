from fastapi import APIRouter, Request
from mcp.server.sse import SseServerTransport
from starlette.responses import Response

from app.mcp.server import mcp

router = APIRouter(tags=["MCP SSE"])

sse_transport = SseServerTransport("/mcp/messages")


@router.get("/sse")
async def handle_sse(request: Request):
    server = mcp._mcp_server

    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options(),
        )

    return Response()


messages_app = sse_transport.handle_post_message
