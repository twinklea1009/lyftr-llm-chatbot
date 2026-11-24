def test_unknown_session_returns_404(client):
    resp = client.get("/sessions/unknown-session-123/messages")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "session not found"}

def test_multiturn_session_history_and_context(client, mock_llm_completion):
    session_id = "s-multiturn-test"

    # Turn 1
    resp1 = client.post("/chat", json={
        "session_id": session_id,
        "message": "Hello, my name is Alice"
    })
    assert resp1.status_code == 200

    # Turn 2
    resp2 = client.post("/chat", json={
        "session_id": session_id,
        "message": "What is my name?"
    })
    assert resp2.status_code == 200

    # Verify history endpoint
    hist_resp = client.get(f"/sessions/{session_id}/messages")
    assert hist_resp.status_code == 200
    hist = hist_resp.json()
    assert hist["session_id"] == session_id
    msgs = hist["messages"]
    assert len(msgs) == 4

    # Oldest first
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello, my name is Alice"
    assert msgs[0].get("metadata") is None

    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Mocked response to: Hello, my name is Alice"
    assert msgs[1]["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert "input_tokens" in msgs[1]["metadata"]
    assert "output_tokens" in msgs[1]["metadata"]

    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"] == "What is my name?"

    assert msgs[3]["role"] == "assistant"
    assert msgs[3]["content"] == "Mocked response to: What is my name?"

    # Verify that in turn 2, the messages passed to LLM included full history
    assert mock_llm_completion.call_count == 2
    last_call_messages = mock_llm_completion.call_args[1]["messages"]
    roles = [m["role"] for m in last_call_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert last_call_messages[1]["content"] == "Hello, my name is Alice"
    assert last_call_messages[3]["content"] == "What is my name?"
