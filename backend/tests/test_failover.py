def test_failover_hook_key_1_429(client, mock_llm_completion):
    resp = client.post(
        "/chat",
        json={"session_id": "s-failover-1", "message": "Test failover 429"},
        headers={"X-Simulate-Failure": "key_1=429"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"

def test_failover_hook_key_1_500(client, mock_llm_completion):
    resp = client.post(
        "/chat",
        json={"session_id": "s-failover-2", "message": "Test failover 500"},
        headers={"X-Simulate-Failure": "key_1=500"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1

def test_failover_hook_all_keys_failed_503(client, mock_llm_completion):
    session_id = "s-failover-all"
    resp = client.post(
        "/chat",
        json={"session_id": session_id, "message": "Test fail all"},
        headers={"X-Simulate-Failure": "*=429"}
    )
    assert resp.status_code == 503
    assert resp.json() == {"detail": "all providers unavailable"}

    # Nothing must be added to SQLite history
    hist = client.get(f"/sessions/{session_id}/messages")
    assert hist.status_code == 404

def test_real_exception_auto_fallback(client, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import litellm

    call_keys = []

    async def fallback_sim(model, messages, api_key, **kwargs):
        call_keys.append(api_key)
        if api_key == "mock_key_1":
            raise Exception("RateLimitError: 429 quota exhausted")
        # key 2 succeeds
        mock_choice = MagicMock()
        mock_choice.message.content = "Recovered from fallback"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 15
        mock_usage.completion_tokens = 5
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage = mock_usage
        return mock_resp

    monkeypatch.setattr(litellm, "acompletion", AsyncMock(side_effect=fallback_sim))

    resp = client.post(
        "/chat",
        json={"session_id": "s-auto-fallback", "message": "Test real error"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == "Recovered from fallback"
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1
    assert call_keys == ["mock_key_1", "mock_key_2"]
