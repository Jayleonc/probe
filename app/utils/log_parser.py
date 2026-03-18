import re

# UNKNOWN(9827,6062) 03-02T12:11:20.5801 <SnWCax0iwhiYZPO4RNsA.NWtYBR> INF impl/topic.go:363:..func message
LOG_PATTERN = re.compile(
    r"^(\w+)\((\d+),(\d+)\)\s+"           # process(pid,tid)
    r"(\d{2}-\d{2}T[\d:.]+)\s+"           # timestamp MM-DDThh:mm:ss.ssss
    r"(?:<([^>]+)>\s+)?"                   # optional <request_id>
    r"(INF|WAR|ERR|DBG)\s+"               # level
    r"(\S+)\s+"                            # source file:line:func
    r"(.*)"                                # message
)


def parse_log_line(line: str) -> dict | None:
    m = LOG_PATTERN.match(line.strip())
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
        "message": m.group(8),
    }
