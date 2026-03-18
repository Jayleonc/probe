import json
from mcp.server.fastmcp import FastMCP

from app.services import log_service

mcp = FastMCP("probe")


@mcp.tool(name="list_services")
async def list_services() -> str:
    """列出当前服务器上所有由 supervisor 管理的服务清单。
    调用此工具了解可查询的服务范围。"""
    result = log_service.get_services()
    return json.dumps(result, ensure_ascii=False)


@mcp.tool(name="search_logs")
async def search_logs(
    keyword: str,
    start_time: str | None = None,
    end_time: str | None = None,
    level: str | None = None,
    limit: int = 20,
) -> str:
    """根据关键词搜索日志，支持按时间范围和日志级别过滤。用于排查报错、定位问题。

    Args:
        keyword: 搜索关键词（如服务名、错误信息、关键字等）
        start_time: 开始时间，ISO格式如 '2026-03-18T15:00:00'，默认最近1小时
        end_time: 结束时间，ISO格式，默认当前时间
        level: 日志级别过滤 (INF/WAR/ERR/DBG)，不填则不过滤
        limit: 最大返回条数，默认20，上限50
    """
    result = await log_service.search_logs(keyword, start_time, end_time, level, limit)
    return json.dumps(result.model_dump(), ensure_ascii=False)


@mcp.tool(name="search_by_request_id")
async def search_by_request_id(
    request_id: str,
    back_hours: int = 0,
) -> str:
    """根据请求ID（request_id / trace_id / hint）搜索一条请求的完整链路日志。
    这是最常用的排障方式：拿到一个请求ID，查出这条请求经过的所有服务和处理过程。

    Args:
        request_id: 请求ID，如 '7n8dpbl2SRiZmnpytX4A' 或 'SnWCax0iwhiYZPO4RNsA.NWtYBR'
        back_hours: 往前搜索的小时数，0表示默认范围，适当增大可搜索更早的日志
    """
    result = await log_service.search_by_request_id(request_id, back_hours)
    return json.dumps(result.model_dump(), ensure_ascii=False)


@mcp.tool(name="tail_errors")
async def tail_errors(
    hours_back: int = 1,
    keyword: str | None = None,
    limit: int = 30,
) -> str:
    """查看最近的错误日志（ERR级别）。用于快速了解某段时间内系统是否有异常。

    Args:
        hours_back: 往前查看多少小时，默认1小时
        keyword: 可选的额外关键词过滤（如服务名'hlopen'、错误类型'timeout'等）
        limit: 最大返回条数，默认30，上限50
    """
    result = await log_service.tail_errors(hours_back, keyword, limit)
    return json.dumps(result.model_dump(), ensure_ascii=False)


@mcp.tool(name="context_around_match")
async def context_around_match(
    file: str,
    line_number: int,
    before: int = 10,
    after: int = 10,
) -> str:
    """查看某条日志命中行的上下文（前后若干行），用于还原事件的前因后果。

    Args:
        file: 日志文件路径（从搜索结果中获取）
        line_number: 行号（从搜索结果中获取）
        before: 向前取多少行，默认10
        after: 向后取多少行，默认10
    """
    result = log_service.get_context(file, line_number, before, after)
    return json.dumps(result, ensure_ascii=False)
