def test_response_caching_across_sessions(client, mock_llm_completion):
    # Session 1: initial message
    resp1 = client.post("/chat", json={
        "session_id": "s-caching-1",
        "message": "What is the capital of France?"
    })
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert data1["metadata"]["key_id"] == "key_1"
    assert mock_llm_completion.call_count == 1

    # Session 2: identical first message sent in a new session
    resp2 = client.post("/chat", json={
        "session_id": "s-caching-2",
        "message": "What is the capital of France?"
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    # Contract: identical reply, LLM_CACHE, key_id is null, fallback_attempts is 0
    assert data2["reply"] == data1["reply"]
    assert data2["metadata"]["resolution_source"] == "LLM_CACHE"
    assert data2["metadata"]["key_id"] is None
    assert data2["metadata"]["fallback_attempts"] == 0
    assert data2["metadata"]["input_tokens"] == data1["metadata"]["input_tokens"]
    assert data2["metadata"]["output_tokens"] == data1["metadata"]["output_tokens"]
    # LLM completion was NOT called again
    assert mock_llm_completion.call_count == 1

def test_different_message_is_cache_miss(client, mock_llm_completion):
    client.post("/chat", json={
        "session_id": "s-caching-3",
        "message": "What is the capital of France?"
    })
    assert mock_llm_completion.call_count == 1

    # Different message
    resp = client.post("/chat", json={
        "session_id": "s-caching-4",
        "message": "What is the capital of Germany?"
    })
    assert resp.status_code == 200
    assert resp.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert mock_llm_completion.call_count == 2
