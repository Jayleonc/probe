import json
import sys
from datetime import datetime, timedelta

from app.adapters import file_adapter, glog_adapter
from app.core.config import settings
from app.schemas.probe import LogItem, SearchResult
from app.utils.log_parser import parse_log_line
from app.utils.redact import redact_text


def _maybe_redact(text: str) -> str:
    if settings.security.redact_enabled:
        return redact_text(text)
    return text


def _audit(tool: str, params: dict, result_count: int, truncated: bool, error: str = ""):
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
        print(f"Audit log write failed: {e}", file=sys.stderr)


def _raw_lines_to_items(
    lines: list[str],
    file: str = "",
    line_numbers: list[int] | None = None,
) -> list[LogItem]:
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
                text=_maybe_redact(line.strip()),
                file=file,
                line_number=ln,
            ))
    return items


def _grep_results_to_items(results: list[tuple[str, int, str]]) -> list[LogItem]:
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
                text=_maybe_redact(text.strip()),
                file=filename,
                line_number=line_num,
            ))
    return items


async def search_by_request_id(request_id: str, back_hours: int = 0) -> SearchResult:
    params = {"request_id": request_id, "back_hours": back_hours}
    try:
        raw = await glog_adapter.glog_search(request_id, back_hours)
        lines = [l for l in raw.splitlines() if l.strip()]

        total = len(lines)
        limit = settings.limits.max_lines
        truncated = total > limit
        lines = lines[:limit]

        items = _raw_lines_to_items(lines)

        _audit("search_by_request_id", params, total, truncated)
        return SearchResult(
            query=params,
            summary={"total_matches": total, "returned": len(items), "truncated": truncated},
            items=items,
            next_actions=["context_around_match"],
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
            f"Time range {hours_diff:.1f}h exceeds max {settings.limits.max_time_range_hours}h"
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
    services = file_adapter.list_supervisor_services()
    _audit("list_services", {}, len(services), False)
    return {"services": services}
