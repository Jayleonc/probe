import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import settings


def get_hourly_files(start_time: datetime, end_time: datetime) -> list[Path]:
    log_dir = Path(settings.paths.hourly_log_dir)
    files = []
    current = start_time.replace(minute=0, second=0, microsecond=0)
    while current <= end_time:
        filename = current.strftime("%Y%m%d%H") + ".log"
        filepath = log_dir / filename
        if filepath.exists():
            files.append(filepath)
        current += timedelta(hours=1)
    return files


def get_recent_hourly_files(hours_back: int = 1) -> list[Path]:
    now = datetime.now()
    start = now - timedelta(hours=hours_back)
    return get_hourly_files(start, now)


async def grep_files(
    files: list[Path],
    pattern: str,
    max_lines: int = 50,
    extra_args: list[str] | None = None,
) -> list[tuple[str, int, str]]:
    """Grep across files. Returns list of (filename, line_number, line_text)."""
    if not files:
        return []

    cmd = ["grep", "-n"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(pattern)
    cmd.extend(str(f) for f in files)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, _ = await asyncio.wait_for(
            proc.communicate(),
            timeout=settings.limits.command_timeout_seconds,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError("grep timed out")

    results = []
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if len(results) >= max_lines:
            break
        # Format: filename:line_number:content (when multiple files)
        # or: line_number:content (when single file)
        if len(files) == 1:
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[0].isdigit():
                results.append((str(files[0]), int(parts[0]), parts[1]))
        else:
            parts = line.split(":", 2)
            if len(parts) >= 3 and parts[1].isdigit():
                results.append((parts[0], int(parts[1]), parts[2]))

    return results


def _validate_file_path(file_path: str) -> Path:
    p = Path(file_path).resolve()
    allowed = [
        Path(settings.paths.hourly_log_dir).resolve(),
        Path(settings.paths.supervisor_log_dir).resolve(),
    ]
    for base in allowed:
        try:
            p.relative_to(base)
            return p
        except ValueError:
            continue
    raise ValueError(f"Access denied: {file_path} is not in allowed directories")


def read_context(file_path: str, line_number: int, before: int = 10, after: int = 10) -> dict:
    p = _validate_file_path(file_path)

    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    start = max(1, line_number - before)
    end = line_number + after

    lines_before = []
    match_line = ""
    lines_after = []

    with open(p) as f:
        for i, line in enumerate(f, 1):
            if i < start:
                continue
            if i > end:
                break
            text = line.rstrip("\n")
            if i < line_number:
                lines_before.append(text)
            elif i == line_number:
                match_line = text
            else:
                lines_after.append(text)

    return {
        "before": lines_before,
        "match": match_line,
        "after": lines_after,
    }


def list_supervisor_services() -> list[str]:
    sup_dir = Path(settings.paths.supervisor_log_dir)
    if not sup_dir.exists():
        return []

    services = set()
    for f in sup_dir.iterdir():
        name = f.name
        if "-stdout---supervisor-" in name:
            service = name.split("-stdout---supervisor-")[0]
            services.add(service)

    return sorted(services)
