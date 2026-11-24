from typing import Optional, List, Literal, Union
from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    session_id: str
    message: str
    system_prompt: Optional[str] = None

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        trimmed = v.strip()
        if not (1 <= len(trimmed) <= 128):
            raise ValueError("session_id must be between 1 and 128 characters")
        return trimmed

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        trimmed = v.strip()
        if not (1 <= len(trimmed) <= 4000):
            raise ValueError("message must be between 1 and 4000 characters after trimming whitespace")
        return trimmed

class ChatResponseMetadata(BaseModel):
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str] = None
    fallback_attempts: int

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatResponseMetadata

class HealthResponse(BaseModel):
    status: str
    keys_configured: int
    cache_enabled: bool

class AssistantMessageMetadata(BaseModel):
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    input_tokens: int
    output_tokens: int

class SessionMessageItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    metadata: Optional[AssistantMessageMetadata] = None

class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: List[SessionMessageItem]

class ErrorDetail(BaseModel):
    detail: Union[str, list, dict]
