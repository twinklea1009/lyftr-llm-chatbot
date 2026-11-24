import React, { useState, useEffect, useRef } from 'react';

// Generates a random session ID on page load: e.g. 's-' + 8 random hex chars
const generateSessionId = () => {
  return 's-' + Math.random().toString(36).substring(2, 10);
};

// Base backend URL from environment or default local port 8000
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export default function App() {
  const [sessionId, setSessionId] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [simulateFailure, setSimulateFailure] = useState('');
  const [backendHealth, setBackendHealth] = useState(null);
  const messagesEndRef = useRef(null);

  // Initialize new session on page load
  useEffect(() => {
    const newSession = generateSessionId();
    setSessionId(newSession);
    checkHealth();
  }, []);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const checkHealth = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/health`);
      if (res.ok) {
        const data = await res.json();
        setBackendHealth(data);
      } else {
        setBackendHealth({ status: 'error' });
      }
    } catch {
      setBackendHealth({ status: 'offline' });
    }
  };

  const startNewSession = () => {
    const newSession = generateSessionId();
    setSessionId(newSession);
    setMessages([]);
  };

  const fetchSessionHistory = async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(`${BACKEND_URL}/sessions/${sessionId}/messages`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      } else {
        const err = await res.json();
        alert(`History error: ${err.detail || 'Not found'}`);
      }
    } catch (e) {
      alert(`Failed to fetch history: ${e.message}`);
    }
  };

  const handleSend = async (e) => {
    if (e) e.preventDefault();
    const trimmed = inputMessage.trim();
    if (!trimmed || isLoading) return;

    // Immediately empty the input according to spec
    setInputMessage('');

    // Append user message locally
    const userMsg = { role: 'user', content: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const headers = {
        'Content-Type': 'application/json',
      };
      if (simulateFailure) {
        headers['X-Simulate-Failure'] = simulateFailure;
      }

      const payload = {
        session_id: sessionId,
        message: trimmed,
      };
      if (systemPrompt.trim()) {
        payload.system_prompt = systemPrompt.trim();
      }

      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (!res.ok) {
        // Display readable error message in chat (never a blank screen)
        const errorDetail = typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail);

        setMessages((prev) => [
          ...prev,
          {
            role: 'error',
            content: `Error (${res.status}): ${errorDetail || 'Request failed'}`,
          },
        ]);
      } else {
        // Append assistant message with full metadata
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: data.reply,
            metadata: data.metadata,
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'error',
          content: `Network Error: ${err.message || 'Unable to connect to backend'}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="app-header">
        <div className="header-brand">
          <span className="brand-badge">LYFTR AI</span>
          <h1 className="brand-title">Resilient LLM Chatbot</h1>
        </div>

        <div className="header-actions">
          <div className="status-pill">
            <span
              className={`status-dot ${
                backendHealth?.status === 'ok' ? 'online' : 'offline'
              }`}
            />
            <span>
              {backendHealth?.status === 'ok'
                ? `Online (${backendHealth.keys_configured} keys, Cache: ${backendHealth.cache_enabled ? 'ON' : 'OFF'})`
                : 'Connecting...'}
            </span>
          </div>

          <div className="status-pill">
            <span>Session: <strong>{sessionId}</strong></span>
          </div>

          <button
            type="button"
            className="btn-secondary"
            onClick={startNewSession}
            title="Start fresh conversation with a new session ID"
          >
            + New Session
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={fetchSessionHistory}
            title="Fetch stored SQLite history for current session"
          >
            Sync History
          </button>
        </div>
      </header>

      {/* Control Bar: System Prompt & Failover Simulation Test Hook */}
      <div className="control-bar">
        <div className="control-group system-prompt-box">
          <span className="control-label">System Prompt:</span>
          <input
            type="text"
            className="system-prompt-input"
            data-testid="system-prompt-input"
            placeholder="Set optional session system prompt (e.g. 'Answer like a pirate')"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
        </div>

        <div className="control-group">
          <span className="control-label">Failover Hook:</span>
          <select
            className="simulation-select"
            value={simulateFailure}
            onChange={(e) => setSimulateFailure(e.target.value)}
            title="Simulates key failure via X-Simulate-Failure request header"
          >
            <option value="">None (Normal Inference)</option>
            <option value="key_1=429">Simulate key_1=429 (Rate Limit)</option>
            <option value="key_1=500">Simulate key_1=500 (Internal Error)</option>
            <option value="key_1=429,key_2=500">Simulate key_1=429, key_2=500</option>
            <option value="*=429">Simulate *=429 (All Keys Fail -&gt; 503)</option>
          </select>
        </div>
      </div>

      {/* Chat Messages Window */}
      <main className="chat-window">
        {messages.length === 0 && !isLoading && (
          <div className="empty-chat">
            <h3>Start a Conversation</h3>
            <p>
              Ask anything to test live inference, response caching, key failover, and token tracking.
            </p>
          </div>
        )}

        {messages.map((msg, index) => {
          if (msg.role === 'user') {
            return (
              <div key={index} className="message-row user">
                <div className="user-bubble">{msg.content}</div>
              </div>
            );
          }

          if (msg.role === 'assistant') {
            const meta = msg.metadata || {};
            const isCache = meta.resolution_source === 'LLM_CACHE';
            const hasFailover = (meta.fallback_attempts || 0) > 0;

            return (
              <div key={index} className="message-row assistant">
                <div className="assistant-container" data-testid="assistant-message">
                  <div className="assistant-text">{msg.content}</div>

                  <div className="metadata-grid">
                    {/* meta-source: Exactly LIVE_INFERENCE or LLM_CACHE */}
                    <span
                      className={`meta-badge ${
                        isCache ? 'source-cache' : 'source-live'
                      }`}
                      data-testid="meta-source"
                    >
                      {meta.resolution_source}
                    </span>

                    {/* meta-model: The model value */}
                    <span className="meta-badge">
                      <span className="meta-label">Model:</span>
                      <span data-testid="meta-model">{meta.model || 'unknown'}</span>
                    </span>

                    {/* meta-latency: Latency, e.g. 812 ms */}
                    <span className="meta-badge">
                      <span className="meta-label">Latency:</span>
                      <span data-testid="meta-latency">
                        {meta.latency_ms !== undefined ? `${meta.latency_ms} ms` : '0 ms'}
                      </span>
                    </span>

                    {/* meta-input-tokens: The input_tokens integer */}
                    <span className="meta-badge">
                      <span className="meta-label">Input Tokens:</span>
                      <span data-testid="meta-input-tokens">
                        {meta.input_tokens !== undefined ? meta.input_tokens : 0}
                      </span>
                    </span>

                    {/* meta-output-tokens: The output_tokens integer */}
                    <span className="meta-badge">
                      <span className="meta-label">Output Tokens:</span>
                      <span data-testid="meta-output-tokens">
                        {meta.output_tokens !== undefined ? meta.output_tokens : 0}
                      </span>
                    </span>

                    {/* Additional helpful details: Key ID and Failovers */}
                    {meta.key_id && (
                      <span className="meta-badge">
                        <span className="meta-label">Key:</span> {meta.key_id}
                      </span>
                    )}

                    {hasFailover && (
                      <span className="meta-badge failover">
                        ⚠️ {meta.fallback_attempts} Failover{meta.fallback_attempts > 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          }

          if (msg.role === 'error') {
            return (
              <div key={index} className="message-row assistant">
                <div className="error-bubble">{msg.content}</div>
              </div>
            );
          }

          return null;
        })}

        {isLoading && (
          <div className="message-row assistant">
            <div className="assistant-container">
              <div className="typing-indicator">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      {/* Input Area */}
      <footer className="input-area">
        <form className="input-form" onSubmit={handleSend}>
          <input
            type="text"
            className="chat-input"
            data-testid="chat-input"
            placeholder="Type your message... (Press Enter to send)"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            disabled={isLoading}
            autoFocus
          />
          <button
            type="submit"
            className="send-button"
            data-testid="send-button"
            disabled={isLoading || !inputMessage.trim()}
          >
            {isLoading ? 'Processing...' : 'Send'}
          </button>
        </form>
      </footer>
    </div>
  );
}
