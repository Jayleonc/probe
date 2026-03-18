"""
日志查询业务逻辑

提供按 request_id 追踪、关键词搜索、错误巡检等核心功能。
"""

import json
import sys
from datetime import datetime, timedelta

from app.adapters import file_adapter, glog_adapter
from app.core.config import settings
from app.schemas.probe import LogItem, SearchResult, TraceItem, TraceSummary
from app.utils.log_parser import parse_log_line, _truncate
from app.utils.redact import redact_text


def _maybe_redact(text: str) -> str:
    """按配置决定是否脱敏"""
    if settings.security.redact_enabled:
        return redact_text(text)
    return text


def _audit(tool: str, params: dict, result_count: int, truncated: bool, error: str = ""):
    """写审计日志"""
    entry = {
        "time": datetime.now().isoformat(),
        "tool": tool,
        "params": params,
        "result_count": result_count,
        "truncated": truncated,
        "error": error,
    }
    try:
        with open(settings.server.audit_log_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"审计日志写入失败: {e}", file=sys.stderr)


def _raw_lines_to_items(
    lines: list[str],
    file: str = "",
    line_numbers: list[int] | None = None,
) -> list[LogItem]:
    """将原始日志行批量转为 LogItem"""
    items = []
    for i, line in enumerate(lines):
        parsed = parse_log_line(line)
        ln = line_numbers[i] if line_numbers and i < len(line_numbers) else 0
        if parsed:
            items.append(LogItem(
                timestamp=parsed["timestamp"],
                level=parsed["level"],
                request_id=parsed["request_id"],
                source=parsed["source"],
                text=_maybe_redact(parsed["message"]),
                file=file,
                line_number=ln,
            ))
        else:
            items.append(LogItem(
                timestamp="",
                level="",
                text=_maybe_redact(_truncate(line.strip())),
                file=file,
                line_number=ln,
            ))
    return items


def _grep_results_to_items(results: list[tuple[str, int, str]]) -> list[LogItem]:
    """将 grep 结果转为 LogItem 列表"""
    items = []
    for filename, line_num, text in results:
        parsed = parse_log_line(text)
        if parsed:
            items.append(LogItem(
                timestamp=parsed["timestamp"],
                level=parsed["level"],
                request_id=parsed["request_id"],
                source=parsed["source"],
                text=_maybe_redact(parsed["message"]),
                file=filename,
                line_number=line_num,
            ))
        else:
            items.append(LogItem(
                timestamp="",
                level="",
                text=_maybe_redact(_truncate(text.strip())),
                file=filename,
                line_number=line_num,
            ))
    return items


def _parsed_to_trace_item(parsed: dict) -> TraceItem:
    """将 parse_log_line 的结果转为精简的 TraceItem"""
    return TraceItem(
        timestamp=parsed["timestamp"],
        level=parsed["level"],
        service=parsed["process"],
        source=parsed["source"],
        message=_maybe_redact(parsed["message"]),
        request_id=parsed["request_id"],
    )


async def search_by_request_id(request_id: str, back_hours: int = 0) -> TraceSummary:
    """
    按 request_id 搜索完整请求链路。

    返回结构化摘要：
    - errors/warns: 完整保留，Agent 第一时间看到问题
    - timeline: 全链路精简时间线，快速了解流转过程
    - services: 经过的服务列表
    """
    params = {"request_id": request_id, "back_hours": back_hours}
    try:
        raw = await glog_adapter.glog_search(request_id, back_hours)
        lines = [l for l in raw.splitlines() if l.strip()]
        total = len(lines)

        # 分类：错误 / 警告 / 普通
        errors: list[TraceItem] = []
        warns: list[TraceItem] = []
        timeline: list[TraceItem] = []
        services_seen: list[str] = []  # 保持顺序的去重列表

        for line in lines:
            parsed = parse_log_line(line)
            if not parsed:
                continue

            item = _parsed_to_trace_item(parsed)

            # 记录服务出现顺序
            if item.service not in services_seen:
                services_seen.append(item.service)

            if parsed["level"] == "ERR":
                errors.append(item)
            elif parsed["level"] == "WAR":
                warns.append(item)
            else:
                timeline.append(item)

        _audit("search_by_request_id", params, total, False)
        return TraceSummary(
            request_id=request_id,
            total_lines=total,
            services=services_seen,
            error_count=len(errors),
            warn_count=len(warns),
            errors=errors,
            warns=warns,
            timeline=timeline,
            next_actions=["search_logs", "context_around_match"],
        )
    except Exception as e:
        _audit("search_by_request_id", params, 0, False, str(e))
        raise


async def search_logs(
    keyword: str,
    start_time: str | None = None,
    end_time: str | None = None,
    level: str | None = None,
    limit: int = 20,
) -> SearchResult:
    """按关键词搜索日志，支持时间范围和级别过滤"""
    limit = min(limit, settings.limits.max_lines)

    now = datetime.now()
    if end_time:
        end_dt = datetime.fromisoformat(end_time)
    else:
        end_dt = now
    if start_time:
        start_dt = datetime.fromisoformat(start_time)
    else:
        start_dt = end_dt - timedelta(hours=1)

    hours_diff = (end_dt - start_dt).total_seconds() / 3600
    if hours_diff > settings.limits.max_time_range_hours:
        raise ValueError(
            f"时间范围 {hours_diff:.1f}h 超过上限 {settings.limits.max_time_range_hours}h"
        )

    params = {
        "keyword": keyword,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "level": level,
        "limit": limit,
    }

    try:
        files = file_adapter.get_hourly_files(start_dt, end_dt)
        if not files:
            _audit("search_logs", params, 0, False)
            return SearchResult(
                query=params,
                summary={"total_matches": 0, "returned": 0, "truncated": False},
                items=[],
            )

        if level:
            pattern = f"{level.upper()}.*{keyword}|{keyword}.*{level.upper()}"
            results = await file_adapter.grep_files(files, pattern, limit, ["-E"])
        else:
            results = await file_adapter.grep_files(files, keyword, limit)

        total = len(results)
        truncated = total >= limit
        items = _grep_results_to_items(results)

        _audit("search_logs", params, total, truncated)
        return SearchResult(
            query=params,
            summary={"total_matches": total, "returned": len(items), "truncated": truncated},
            items=items,
            next_actions=["context_around_match", "search_by_request_id"],
        )
    except Exception as e:
        _audit("search_logs", params, 0, False, str(e))
        raise


async def tail_errors(hours_back: int = 1, keyword: str | None = None, limit: int = 30) -> SearchResult:
    """查看最近的错误日志"""
    limit = min(limit, settings.limits.max_lines)
    params = {"hours_back": hours_back, "keyword": keyword, "limit": limit}

    try:
        files = file_adapter.get_recent_hourly_files(hours_back)
        if not files:
            _audit("tail_errors", params, 0, False)
            return SearchResult(
                query=params,
                summary={"total_matches": 0, "returned": 0, "truncated": False},
                items=[],
            )

        pattern = f"ERR.*{keyword}" if keyword else "ERR"
        results = await file_adapter.grep_files(files, pattern, limit, ["-E"])

        total = len(results)
        truncated = total >= limit
        items = _grep_results_to_items(results)

        _audit("tail_errors", params, total, truncated)
        return SearchResult(
            query=params,
            summary={"total_matches": total, "returned": len(items), "truncated": truncated},
            items=items,
            next_actions=["context_around_match", "search_by_request_id"],
        )
    except Exception as e:
        _audit("tail_errors", params, 0, False, str(e))
        raise


def get_context(file: str, line_number: int, before: int = 10, after: int = 10) -> dict:
    """读取某行日志的上下文"""
    before = min(before, 50)
    after = min(after, 50)

    params = {"file": file, "line_number": line_number, "before": before, "after": after}
    try:
        ctx = file_adapter.read_context(file, line_number, before, after)
        if settings.security.redact_enabled:
            ctx["before"] = [redact_text(l) for l in ctx["before"]]
            ctx["match"] = redact_text(ctx["match"])
            ctx["after"] = [redact_text(l) for l in ctx["after"]]

        _audit("context_around_match", params, 1, False)
        return {
            "file": file,
            "line_number": line_number,
            "context": ctx,
        }
    except Exception as e:
        _audit("context_around_match", params, 0, False, str(e))
        raise


def get_services() -> dict:
    """获取 supervisor 管理的服务列表"""
    services = file_adapter.list_supervisor_services()
    _audit("list_services", {}, len(services), False)
    return {"services": services}
