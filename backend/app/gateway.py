import os
import time
import logging
from typing import Dict, List, Optional, Tuple, Any

# Ensure LiteLLM uses local cost map and minimal telemetry
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
import litellm
from litellm.caching.caching import Cache

from app.config import settings
from app.models import ChatResponseMetadata

logger = logging.getLogger("uvicorn.error")

# Configure LiteLLM
litellm.telemetry = False
litellm.drop_params = True
litellm.suppress_debug_info = True

# Initialize in-memory / local cache
cache = Cache(type="local")
litellm.cache = cache

def parse_simulate_failure_header(header_val: Optional[str]) -> Dict[str, int]:
    """
    Parses X-Simulate-Failure header:
    e.g. 'key_1=429', 'key_1=429,key_2=500', '*=429'
    Allowed statuses: 429, 500, 502, 503
    """
    if not header_val or not settings.enable_failure_simulation:
        return {}
    
    simulations = {}
    parts = [p.strip() for p in header_val.split(",") if p.strip()]
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            try:
                status = int(v)
                if status in (429, 500, 502, 503):
                    simulations[k] = status
            except ValueError:
                continue
    return simulations

class LLMGateway:
    def __init__(self):
        self.cache = cache

    def is_cache_enabled(self) -> bool:
        return self.cache is not None

    def get_configured_keys_count(self) -> int:
        return len(settings.key_pool)

    def compute_cache_key(self, model: str, messages: List[dict]) -> str:
        # Canonical cache key: model + full message list sent to LLM
        return self.cache.get_cache_key(model=model, messages=messages)

    async def execute_chat(
        self,
        messages: List[dict],
        simulate_failure_header: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> Tuple[str, ChatResponseMetadata]:
        """
        Executes chat request with LiteLLM caching and key fallback.
        Returns (reply_text, metadata).
        Raises HTTPException(status_code=503) if all keys fail.
        """
        start_time = time.perf_counter()
        model = model_override or settings.default_model

        simulated_failures = parse_simulate_failure_header(simulate_failure_header)
        is_simulation_active = bool(simulated_failures)

        cache_key = self.compute_cache_key(model=model, messages=messages)

        # 1. Check response cache if simulation is not explicitly testing key failover
        if not is_simulation_active:
            cached_entry = self.cache.get_cache(cache_key=cache_key)
            if cached_entry and isinstance(cached_entry, dict) and "reply" in cached_entry:
                latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
                metadata = ChatResponseMetadata(
                    resolution_source="LLM_CACHE",
                    model=model,
                    latency_ms=latency_ms,
                    input_tokens=cached_entry.get("input_tokens", 0),
                    output_tokens=cached_entry.get("output_tokens", 0),
                    key_id=None,
                    fallback_attempts=0
                )
                return cached_entry["reply"], metadata

        # 2. Iterate through key pool with fallback
        key_pool = settings.key_pool
        fallback_attempts = 0
        last_error = None

        for key_id, raw_api_key in key_pool:
            # Check if this key is simulated to fail
            simulated_status = simulated_failures.get(key_id) or simulated_failures.get("*")
            if simulated_status:
                logger.info(f"Simulating failure {simulated_status} for key {key_id}")
                fallback_attempts += 1
                last_error = f"Simulated {simulated_status}"
                continue

            try:
                # Call LiteLLM completion
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    api_key=raw_api_key,
                    temperature=0.7,
                )

                # Extract reply text
                reply = ""
                if response.choices and len(response.choices) > 0:
                    reply = response.choices[0].message.content or ""
                
                # Extract tokens
                input_tokens = 0
                output_tokens = 0
                if hasattr(response, "usage") and response.usage:
                    input_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                    output_tokens = getattr(response.usage, "completion_tokens", 0) or 0
                
                if input_tokens == 0:
                    try:
                        input_tokens = litellm.token_counter(model=model, messages=messages)
                    except Exception:
                        input_tokens = sum(len(m.get("content", "").split()) for m in messages)
                
                if output_tokens == 0:
                    try:
                        output_tokens = litellm.token_counter(model=model, text=reply)
                    except Exception:
                        output_tokens = len(reply.split())

                latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))

                # Store successful result in cache
                self.cache.add_cache(
                    {
                        "reply": reply,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    },
                    cache_key=cache_key
                )

                metadata = ChatResponseMetadata(
                    resolution_source="LIVE_INFERENCE",
                    model=model,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    key_id=key_id,
                    fallback_attempts=fallback_attempts
                )
                return reply, metadata

            except Exception as e:
                logger.warning(f"Error calling LLM with key {key_id}: {e}")
                fallback_attempts += 1
                last_error = str(e)
                continue

        # If every key in pool failed
        logger.error(f"All providers unavailable. Attempts: {fallback_attempts}, Last error: {last_error}")
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="all providers unavailable")

gateway = LLMGateway()
