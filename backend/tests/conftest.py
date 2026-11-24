import os
import sys

# Ensure backend root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["LLM_API_KEYS"] = "mock_key_1,mock_key_2"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

import litellm
from app.config import settings
from app.database import init_db
from app.gateway import gateway
from app.main import app

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    # Use isolated sqlite database per test
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")
    monkeypatch.setattr(settings, "llm_api_keys", "mock_key_1,mock_key_2")
    monkeypatch.setattr(settings, "enable_failure_simulation", True)
    
    # Clear cache before each test
    from litellm.caching.caching import Cache
    gateway.cache = Cache(type="local")
    litellm.cache = gateway.cache

    init_db()

@pytest.fixture
def mock_llm_completion(monkeypatch):
    """
    Provides mock for litellm.acompletion that generates deterministic responses
    based on the last user message.
    """
    async def fake_acompletion(model, messages, api_key, **kwargs):
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        reply_text = f"Mocked response to: {last_user}"
        if "capital of France" in last_user:
            reply_text = "The capital of France is Paris."

        mock_choice = MagicMock()
        mock_choice.message.content = reply_text

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = len(last_user.split()) + 30
        mock_usage.completion_tokens = len(reply_text.split())

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        return mock_response

    mock_func = AsyncMock(side_effect=fake_acompletion)
    monkeypatch.setattr(litellm, "acompletion", mock_func)
    return mock_func

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
