import asyncio
import re

from app.core.config import settings

SAFE_INPUT = re.compile(r"^[a-zA-Z0-9._\-]{1,256}$")


def _validate_input(value: str) -> str:
    if not SAFE_INPUT.match(value):
        raise ValueError(f"Input contains unsafe characters: {value!r}")
    return value


async def glog_search(request_id: str, back_hours: int = 0) -> str:
    _validate_input(request_id)
    glog_path = settings.paths.glog_path

    cmd = [glog_path]
    if back_hours > 0:
        cmd.extend(["-b", str(back_hours)])
    cmd.append(request_id)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=settings.limits.command_timeout_seconds,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"glog.sh timed out after {settings.limits.command_timeout_seconds}s")

    return stdout.decode("utf-8", errors="replace")
