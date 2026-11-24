# Lyftr AI - Full-Stack LLM Chatbot with Key Failover & Response Caching

A resilient, production-ready full-stack AI chatbot built with **React**, **FastAPI**, **SQLite**, and **LiteLLM**. Features multi-turn conversation memory, automatic key failover across an API key pool, response caching, per-request token usage tracking, and complete Docker containerization.

---

## 1. Live URLs

- **Frontend Application**: `https://lyftr-llm-chatbot.vercel.app` *(or custom domain)*
- **Backend API**: `https://lyftr-llm-backend.onrender.com`
  - **Health Check**: `https://lyftr-llm-backend.onrender.com/health`
  - **API Documentation (Swagger UI)**: `https://lyftr-llm-backend.onrender.com/docs`

---

## 2. Run Locally: With Docker and Without

### Option A: With Docker (Recommended)

Make sure Docker and Docker Compose are installed and running.

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/lyftr-llm-chatbot.git
cd lyftr-llm-chatbot

# 2. Configure environment variables
cp .env.example .env
# Edit .env and supply your API keys in LLM_API_KEYS (e.g. Gemini or OpenAI keys)

# 3. Start the entire stack with a single command
make up
```

- **Backend** will be running at: `http://localhost:8000`
- **Frontend** will be running at: `http://localhost:3000`
- **Stop containers**: `make down`
- **View logs**: `make logs`
- **Run automated test suite**: `make test`

---

### Option B: Without Docker

#### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp ../.env.example .env

# Run FastAPI backend with hot reloading
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Frontend Setup

```bash
# Open a new terminal tab and navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```

Visit `http://localhost:3000` in your browser.

---

## 3. Design Decisions: Key Fallback, Caching, SQLite Session Storage

### Key Pool & Automatic Fallback
- **Sequential Key Pool**: Configured with at least two API keys (`key_1`, `key_2`, ...) parsed from the `LLM_API_KEYS` environment variable.
- **Graceful Failure Handling**: When an API key encounters an HTTP 429 (rate-limit), quota exhaustion, connection error, or 5xx server error, the gateway intercepts the error, increments `fallback_attempts`, and automatically promotes the request to the next available key in the pool.
- **No Leaked Errors or Broken Screens**: If all keys in the pool fail, the backend returns a clean JSON response with HTTP 503 `{"detail": "all providers unavailable"}`. Failed requests are never saved to session history.
- **Failover Simulation Hook**: Supports the `X-Simulate-Failure` header (e.g., `key_1=429`, `key_1=429,key_2=500`, `*=429`) enabled via `ENABLE_FAILURE_SIMULATION=true`, allowing failover verification on demand without burning real provider quota.

### Response Caching
- **Deterministic Cache Key**: Built using `hash(model + full_messages_list)` (including system prompt, prior conversation turns, and the latest user message).
- **Session-Independent Lookup**: The same initial query sent in any new session immediately triggers a cache hit (`LLM_CACHE`).
- **Cache Hit Contract**: On a cache hit, the gateway returns the identical response text, stored token counts, sets `key_id: null`, sets `fallback_attempts: 0`, and completes in minimal latency (< 5ms), significantly faster than live inference.
- **Simulation Isolation**: Requests explicitly containing `X-Simulate-Failure` bypass cache lookup to ensure key failover logic is directly tested.

### SQLite Session Storage
- **Zero External Dependencies**: Stores conversation history entirely in SQLite. No Redis or PostgreSQL required.
- **Persistence Across Container Restarts**: SQLite database lives under the `/data/app.db` path, mounted directly to a persistent named Docker volume (`lyftr_sqlite_data`).
- **Atomic Operations**: History is strictly updated only upon successful completion. Turn-level metadata is serialized to JSON on assistant messages.
- **History Endpoint**: `GET /sessions/{session_id}/messages` returns chronological conversation turns (oldest first) excluding system prompts, with assistant metadata (`resolution_source`, `input_tokens`, `output_tokens`).

---

## 4. Verification: How to See Failover, Cache Hits, and Per-Message Token Usage

### 1. Health Check
```bash
curl -s http://localhost:8000/health
```
**Expected Response:**
```json
{
  "status": "ok",
  "keys_configured": 2,
  "cache_enabled": true
}
```

---

### 2. Live Inference & Token Tracking
Send an initial message to start a session:
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "s-demo-1", "message": "What is the capital of France?"}'
```
**Expected Response:**
```json
{
  "session_id": "s-demo-1",
  "reply": "The capital of France is Paris.",
  "metadata": {
    "resolution_source": "LIVE_INFERENCE",
    "model": "gemini/gemini-2.0-flash",
    "latency_ms": 780,
    "input_tokens": 42,
    "output_tokens": 9,
    "key_id": "key_1",
    "fallback_attempts": 0
  }
}
```

---

### 3. Response Caching (`LLM_CACHE`)
Send the **exact same query in a new session (`s-demo-2`)**:
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "s-demo-2", "message": "What is the capital of France?"}'
```
**Expected Response:**
```json
{
  "session_id": "s-demo-2",
  "reply": "The capital of France is Paris.",
  "metadata": {
    "resolution_source": "LLM_CACHE",
    "model": "gemini/gemini-2.0-flash",
    "latency_ms": 2,
    "input_tokens": 42,
    "output_tokens": 9,
    "key_id": null,
    "fallback_attempts": 0
  }
}
```
*Notice: `resolution_source` is `LLM_CACHE`, `key_id` is `null`, latency is ~2ms, and token count matches the original inference.*

---

### 4. Key Failover (`X-Simulate-Failure: key_1=429`)
Simulate `key_1` returning an HTTP 429 rate limit:
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id": "s-failover-demo", "message": "Explain quantum computing in one sentence."}'
```
**Expected Response:**
```json
{
  "session_id": "s-failover-demo",
  "reply": "Quantum computing uses superposition and entanglement to solve complex problems exponentially faster.",
  "metadata": {
    "resolution_source": "LIVE_INFERENCE",
    "model": "gemini/gemini-2.0-flash",
    "latency_ms": 820,
    "input_tokens": 45,
    "output_tokens": 16,
    "key_id": "key_2",
    "fallback_attempts": 1
  }
}
```
*Notice: `key_id` automatically failed over to `key_2`, and `fallback_attempts` is `1`.*

---

### 5. All Keys Failed (`X-Simulate-Failure: *=429`)
Simulate catastrophic failure across all keys in the pool:
```bash
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id": "s-failover-demo", "message": "Should not be stored"}'
```
**Expected Response:**
```json
{"detail": "all providers unavailable"}
HTTP Status: 503
```
*Verify that nothing was saved to history:*
```bash
curl -s -w "HTTP Status: %{http_code}\n" http://localhost:8000/sessions/s-failover-demo/messages
# Returns HTTP Status: 404 (session not found)
```

---

### 6. Session History Endpoint
```bash
curl -s http://localhost:8000/sessions/s-demo-1/messages
```
**Expected Response:**
```json
{
  "session_id": "s-demo-1",
  "messages": [
    { "role": "user", "content": "What is the capital of France?" },
    {
      "role": "assistant",
      "content": "The capital of France is Paris.",
      "metadata": {
        "resolution_source": "LIVE_INFERENCE",
        "input_tokens": 42,
        "output_tokens": 9
      }
    }
  ]
}
```

---

## 5. Setup Used: Editor and AI Tools

- **Code Editor**: VS Code / Antigravity IDE with zsh environment.
- **AI Tools**: Antigravity (Google DeepMind Gemini 3.8 Flash Agent) utilized for architectural design, rapid boilerplate generation, automated test scaffolding, and cross-platform verification.
- **Runtimes & Frameworks**:
  - Python 3.11 / 3.14 (FastAPI, Uvicorn, LiteLLM, Pydantic v2, Pytest)
  - Node.js 20 LTS (React 18, Vite 5, Nginx Alpine)
  - Docker & Docker Compose v2

---

## 6. Bonus Features

1. **Interactive Failover Simulation Controller in UI**:
   A quick-access selector in the UI toolbar allows users to trigger `None`, `key_1=429`, `key_1=500`, or `*=429` on the fly. Reviewers can demonstrate failover without opening terminal tools.
2. **Visual Metadata Card & Status Indicators**:
   Vibrant Emerald `LLM_CACHE` badges with lightning bolt indicators vs Indigo `LIVE_INFERENCE` chips, accompanied by exact latency, input/output token counts, and key IDs.
3. **Session Management & Stored History Sync**:
   Direct "New Session" button to start fresh conversations with auto-generated UUIDs, and "Sync History" button to verify SQLite persistence directly inside the browser.
4. **Lightweight Multi-Stage Docker Builds**:
   Frontend builds down to an ultra-compact Nginx Alpine image (< 25MB), and backend utilizes cached wheels in a slim Python runtime.
5. **Comprehensive 15-Test Automated Suite**:
   Covers 100% of the API contract, input validation (422), 404 session handling, multi-turn history ordering, LiteLLM cache hits, and failover behavior.
