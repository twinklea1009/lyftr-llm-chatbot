def test_chat_success(client, mock_llm_completion):
    payload = {
        "session_id": "s-test-1",
        "message": "What is the capital of France?"
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["session_id"] == "s-test-1"
    assert data["reply"] == "The capital of France is Paris."
    meta = data["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["model"] == "gemini/gemini-2.0-flash"
    assert meta["key_id"] == "key_1"
    assert meta["fallback_attempts"] == 0
    assert meta["input_tokens"] > 0
    assert meta["output_tokens"] > 0
    assert isinstance(meta["latency_ms"], int)

def test_chat_message_trimming(client, mock_llm_completion):
    payload = {
        "session_id": "s-trim",
        "message": "   Hello with whitespace   "
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200

def test_chat_validation_empty_message(client):
    payload = {
        "session_id": "s-test-invalid",
        "message": "   "
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()

def test_chat_validation_too_long_message(client):
    payload = {
        "session_id": "s-test-invalid",
        "message": "a" * 4001
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()

def test_chat_validation_empty_session_id(client):
    payload = {
        "session_id": "",
        "message": "Hello"
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()

def test_failed_validation_not_added_to_history(client):
    session_id = "s-invalid-not-stored"
    payload = {
        "session_id": session_id,
        "message": ""
    }
    client.post("/chat", json=payload)
    # Session history must not exist (404)
    history_resp = client.get(f"/sessions/{session_id}/messages")
    assert history_resp.status_code == 404
