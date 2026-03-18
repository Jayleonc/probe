"""
日志行解析器

将 Brick 微服务框架产生的结构化日志行解析为字典。
格式示例: UNKNOWN(9827,6062) 03-02T12:11:20.5801 <SnWCax0iwhiYZPO4RNsA.NWtYBR> INF impl/topic.go:363:..func message
"""

import re

from app.core.config import settings

# Brick 微服务日志正则
LOG_PATTERN = re.compile(
    r"^(\w+)\((\d+),(\d+)\)\s+"           # 进程名(pid,tid)
    r"(\d{2}-\d{2}T[\d:.]+)\s+"           # 时间戳 MM-DDThh:mm:ss.ssss
    r"(?:<([^>]+)>\s+)?"                   # 可选的 <request_id>
    r"(?:\x1b\[\d+m)?"                     # 可选的 ANSI 颜色码开头
    r"(INF|WAR|ERR|DBG)\s+"               # 日志级别
    r"(\S+)"                               # 来源 file:line:func
    r"(?:\x1b\[0m)?"                       # 可选的 ANSI 颜色码结尾
    r"\s+(.*)"                             # 消息正文
)

# ANSI 转义序列清理
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _truncate(text: str) -> str:
    """截断过长的文本，避免 req/resp body 等超长内容浪费 token"""
    max_len = settings.limits.max_line_length
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"...[截断, 原始 {len(text)} 字符]"


def _clean_ansi(text: str) -> str:
    """去除 ANSI 颜色转义序列"""
    return ANSI_ESCAPE.sub("", text)


def parse_log_line(line: str) -> dict | None:
    """
    解析单行日志，返回结构化字典；无法解析则返回 None。
    解析后的 message 会自动截断。
    """
    cleaned = _clean_ansi(line.strip())
    m = LOG_PATTERN.match(cleaned)
    if not m:
        return None
    return {
        "process": m.group(1),
        "pid": m.group(2),
        "tid": m.group(3),
        "timestamp": m.group(4),
        "request_id": m.group(5),
        "level": m.group(6),
        "source": m.group(7),
        "message": _truncate(m.group(8)),
    }
