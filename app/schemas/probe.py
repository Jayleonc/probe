from pydantic import BaseModel


class LogItem(BaseModel):
    timestamp: str
    level: str
    request_id: str | None = None
    source: str = ""
    text: str
    file: str = ""
    line_number: int = 0


class SearchResult(BaseModel):
    query: dict
    summary: dict
    items: list[LogItem]
    next_actions: list[str] = []
