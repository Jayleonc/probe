"""
MCP SSE 传输层

将 FastMCP server 通过 SSE (Server-Sent Events) 协议暴露给客户端。
客户端通过 GET /mcp/sse 建立 SSE 长连接，通过 POST /mcp/messages/ 发送请求。
"""

from fastapi import APIRouter, Request
from mcp.server.sse import SseServerTransport
from starlette.responses import Response

from app.mcp.server import mcp

router = APIRouter(tags=["MCP SSE"])

# 注意：路径末尾带斜杠，与 FastAPI mount 路径保持一致，避免 307 重定向导致初始化时序错乱
sse_transport = SseServerTransport("/mcp/messages/")


@router.get("/sse")
async def handle_sse(request: Request):
    """SSE 连接端点，客户端通过此接口建立长连接"""
    server = mcp._mcp_server

    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options(),
        )

    return Response()


# POST 消息处理器，挂载到 /mcp/messages/
messages_app = sse_transport.handle_post_message
