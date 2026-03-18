import re

REDACT_PATTERNS = [
    (re.compile(r"(token|access_key|secret_key|cookie)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    (re.compile(r"1[3-9]\d{9}"), "***PHONE***"),
    (re.compile(r"\d{17}[\dXx]"), "***ID_CARD***"),
]


def redact_text(text: str) -> str:
    for pattern, replacement in REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_lines(lines: list[str]) -> list[str]:
    return [redact_text(line) for line in lines]
