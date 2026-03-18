from typing import Any, Optional
from pydantic import BaseModel, Field


class ToolInputProperty(BaseModel):
    type: str
    description: str
    enum: Optional[list[Any]] = None
    default: Optional[Any] = None


class ToolInputSchema(BaseModel):
    type: str = "object"
    properties: dict[str, ToolInputProperty]
    required: list[str] = Field(default_factory=list)


class Tool(BaseModel):
    name: str
    description: str
    input_schema: ToolInputSchema


class ToolsListResponse(BaseModel):
    tools: list[Tool]


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any]


class ToolCallContentItem(BaseModel):
    type: str
    text: Optional[str] = None


class ToolCallResponse(BaseModel):
    content: list[ToolCallContentItem]
    is_error: bool


class Resource(BaseModel):
    uri: str
    name: str
    description: str
    mime_type: str


class ResourcesListResponse(BaseModel):
    resources: list[Resource]
