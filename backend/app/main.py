import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import (
    init_db,
    check_db_health,
    get_raw_session_history,
    get_session_messages,
    add_message,
)
from app.gateway import gateway
from app.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SessionHistoryResponse,
)

logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize SQLite schema
    init_db()
    logger.info("Database schema initialized.")
    yield

# Also initialize immediately on module load
try:
    init_db()
except Exception as e:
    logger.warning(f"Initial DB setup deferred: {e}")

app = FastAPI(
    title="Lyftr AI - Resilient LLM Chatbot Gateway",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers ensuring clean JSON responses with 'detail' field
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal server error"},
    )

@app.get("/health", response_model=HealthResponse)
async def health():
    """
    Returns 200 once the app is running, the database is reachable and the key pool is loaded.
    { "status": "ok", "keys_configured": 2, "cache_enabled": true }
    """
    db_ok = check_db_health()
    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unreachable"
        )

    keys_count = gateway.get_configured_keys_count()
    cache_ok = gateway.is_cache_enabled()

    return HealthResponse(
        status="ok",
        keys_configured=keys_count,
        cache_enabled=cache_ok,
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request_body: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
):
    """
    Chat endpoint with multi-turn context, response caching, key failover, and token tracking.
    """
    session_id = request_body.session_id
    user_message = request_body.message

    # 1. Fetch existing session history from SQLite (oldest first)
    history = get_raw_session_history(session_id)

    # 2. Determine system prompt
    effective_system_prompt = request_body.system_prompt or settings.default_system_prompt

    # 3. Build messages list for the LLM
    # Cache key: model + full message list (system prompt + history + new message)
    llm_messages = [{"role": "system", "content": effective_system_prompt}]
    llm_messages.extend(history)
    llm_messages.append({"role": "user", "content": user_message})

    # 4. Execute chat through LiteLLM Gateway
    # If this fails (e.g. 503 all providers unavailable), nothing is added to history!
    reply, metadata = await gateway.execute_chat(
        messages=llm_messages,
        simulate_failure_header=x_simulate_failure,
    )

    # 5. Persist only successful turn to SQLite
    add_message(session_id, "user", user_message)
    add_message(session_id, "assistant", reply, metadata=metadata.model_dump())

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        metadata=metadata,
    )

@app.get("/sessions/{session_id}/messages", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str):
    """
    Returns the stored history of one session from SQLite, oldest first, without the system prompt.
    """
    messages = get_session_messages(session_id)
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="session not found"
        )

    return SessionHistoryResponse(
        session_id=session_id,
        messages=messages,
    )
