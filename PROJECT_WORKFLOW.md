# Guardrail Gateway — Complete Project Workflow and Technical Explanation

## 1. Project overview

`guardrail-gateway` is a Python-based LLM gateway that places security, reliability, policy enforcement, and observability controls between an application user and a hosted language model.

The project accepts chat prompts through a FastAPI API and a Streamlit demonstration interface. Before a prompt reaches the model, it passes through request validation, per-client rate limiting, NVIDIA NeMo Guardrails input checks, and Portkey routing. After the model responds, the output is inspected for API keys, private network addresses, and configured confidential terms. The output can be blocked or redacted depending on the configured policy.

The default model configuration is `openai/gpt-oss-120b`, routed through Portkey to the configured provider. Portkey can also be supplied with a configuration ID for externally managed provider routing, fallback, or weighted traffic policies.

The project is intentionally educational and decoupled. It demonstrates how an enterprise-style LLM gateway can combine:

- FastAPI and Pydantic request validation
- NVIDIA NeMo Guardrails
- Portkey AI Gateway
- Groq-compatible model inference
- Input PII detection
- Prompt-injection heuristics
- Output data-loss prevention
- Secret and internal-IP detection
- In-memory sliding-window rate limiting
- Request timeout enforcement
- Safe operational logging
- Streamlit telemetry and demonstrations
- Offline automated testing with mocked model calls

---

## 2. The problem this project solves

A direct integration has the following shape:

```text
User application -> LLM provider
```

That design makes it difficult to centrally enforce safety and operational policies. Users may submit personal information, attempt jailbreaks, overload the service, or receive information that should not leave an internal system. Provider failures may also leave requests hanging or expose raw credentials in application code.

This project changes the shape to:

```text
User
  -> Streamlit UI or API client
  -> FastAPI validation border
  -> Sliding-window rate limiter
  -> NeMo input guardrails
  -> Portkey AI Gateway
  -> Groq or another configured provider
  -> NeMo output guardrails
  -> Safe structured response
```

The gateway centralizes the controls around the model rather than requiring every client application to implement them independently.

---

## 3. Technology stack

- **Language:** Python
- **Web framework:** FastAPI
- **ASGI server:** Uvicorn
- **Data validation:** Pydantic 2
- **LLM safety framework:** NVIDIA NeMo Guardrails
- **LLM gateway:** Portkey AI Gateway
- **LLM client:** LangChain `ChatOpenAI`
- **Provider/model interface:** OpenAI-compatible API routed through Portkey
- **Frontend:** Streamlit
- **HTTP client:** HTTPX
- **Testing:** Pytest and FastAPI `TestClient`
- **Configuration:** `.env`, Python dataclasses, YAML, and Colang

The main dependencies are declared in `requirements.txt`:

```text
fastapi
uvicorn
pydantic
python-dotenv
portkey-ai
nemoguardrails
langchain-core
langchain-openai
onnxruntime
httpx
pytest
streamlit
```

---

## 4. Repository structure

```text
guardrail-gateway/
├── .env.example
│   Environment-variable template for Portkey and model configuration.
│
├── .gitignore
│   Ignores secrets, virtual environments, caches, and generated files.
│
├── README.md
│   Architecture, setup, features, tests, and production-gap analysis.
│
├── requirements.txt
│   Python dependencies and compatible version ranges.
│
├── app/
│   ├── __init__.py
│   │   Python package marker.
│   │
│   ├── main.py
│   │   FastAPI application, endpoints, rate limiting, timeout handling,
│   │   logging, errors, and response construction.
│   │
│   ├── config.py
│   │   Environment loading and fail-fast settings validation.
│   │
│   ├── schemas.py
│   │   Pydantic request and response contracts.
│   │
│   ├── gateway.py
│   │   Portkey client adapter and connection test helper.
│   │
│   ├── guardrail.py
│   │   NeMo Guardrails initialization and Portkey-backed model setup.
│   │
│   └── policies/
│       ├── __init__.py
│       │   Python package marker.
│       │
│       └── rate_limiter.py
│           In-memory per-client sliding-window limiter.
│
├── config/
│   ├── actions.py
│   │   Deterministic input/output scanning and redaction actions.
│   │
│   ├── config.py
│   │   Custom no-op embedding provider for NeMo Guardrails.
│   │
│   ├── config.yml
│   │   NeMo model, provider, instruction, and rail bindings.
│   │
│   └── rails.co
│       Colang safety flows and refusal messages.
│
├── frontend/
│   └── app.py
│       Streamlit chat dashboard and demo controls.
│
└── tests/
    ├── __init__.py
    │   Python package marker.
    │
    ├── conftest.py
    │   Shared test client and rate-limiter isolation fixture.
    │
    └── test_gateway.py
        API, policy, guardrail, anti-evasion, and redaction tests.
```

---

## 5. End-to-end request workflow

### Step 1: A prompt is submitted

A client can submit a request to the backend:

```http
POST /chat
Content-Type: application/json
```

```json
{
  "prompt": "Explain what an AI guardrail is."
}
```

The Streamlit frontend sends exactly this type of request. It can also use its preset buttons to submit safe, PII, jailbreak, and output-leak demonstrations.

### Step 2: FastAPI validates the body

`app/schemas.py` defines `ChatRequest`:

```python
class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
```

The prompt must contain at least one character and cannot exceed 4,000 characters. Invalid requests receive HTTP `422` before the rate-limiter/model workflow runs.

The response contract is `ChatResponse`:

```json
{
  "response": "Generated text",
  "model": "openai/gpt-oss-120b",
  "gateway": "portkey",
  "latency_ms": 842.13
}
```

### Step 3: The client is identified

`app/main.py` obtains the client IP from `request.client.host`. If the client cannot be identified, it uses `127.0.0.1`.

### Step 4: Rate limiting runs

The global limiter in `app/policies/rate_limiter.py` allows five requests per client in a rolling 60-second window.

For every request it:

1. Gets the current timestamp.
2. Removes timestamps older than the active window.
3. Checks the remaining number of requests.
4. Rejects the request when five requests are already active.
5. Otherwise records the timestamp and allows processing.

Successful responses include:

```http
X-RateLimit-Limit: 5
X-RateLimit-Remaining: 4
X-RateLimit-Reset: 60.0
```

The sixth request within the window receives HTTP `429` and a `Retry-After` header.

The limiter uses process memory and a `deque`. It is appropriate for a single-process demo but is not shared across multiple workers or server instances.

### Step 5: Latency timing starts

After rate limiting, `time.perf_counter()` starts a monotonic timer. The measured duration covers guardrail processing, model routing, upstream inference, and output inspection.

### Step 6: NeMo Guardrails receives the request

The endpoint calls:

```python
await rails.generate_async(
    messages=[{"role": "user", "content": body.prompt}]
)
```

The `rails` singleton comes from `app/guardrail.py`, which:

1. Loads the repository `config/` directory.
2. Reads the YAML/Colang/action configuration.
3. Builds Portkey headers.
4. Creates a LangChain `ChatOpenAI` client.
5. Gives that client to `LLMRails`.

### Step 7: Input guardrails run

The active input flows are:

```yaml
input:
  flows:
    - check input pii
    - check input injection
```

The input PII flow runs first, followed by the prompt-injection flow. A blocked request stops before any provider call, reducing cost and preventing unsafe data from being forwarded.

### Step 8: Safe requests go through Portkey

The LangChain model client uses:

```text
https://api.portkey.ai/v1
```

Portkey acts as the gateway abstraction. It receives the Portkey API key and either a virtual key or configuration ID.

If `PORTKEY_CONFIG_ID` is set, the request uses the Portkey configuration header. Otherwise it uses the Portkey virtual-key header. An external Portkey configuration can manage provider selection, fallback, or weighted routing.

### Step 9: The upstream model generates a response

The configured model is normally:

```text
openai/gpt-oss-120b
```

The LangChain client uses `temperature=0.0` and `max_tokens=256`. The model is reached through Portkey rather than by embedding a raw provider integration in the endpoint.

### Step 10: Output guardrails run

The active output flow is:

```yaml
output:
  flows:
    - block sensitive output
```

The generated text is checked for API keys, private IP addresses, and configured confidential terms. If a leak is found, the response is replaced by a refusal message.

### Step 11: The response is returned

For a safe response, FastAPI calculates latency, adds `X-Response-Time-Ms`, logs safe metadata, and returns `ChatResponse` JSON to the client.

---

## 6. Input guardrails in detail

### 6.1 PII detection

`config/actions.py` defines `check_input_pii`.

It checks for:

- Email addresses
- Domestic phone numbers
- International phone numbers

Examples that are detected:

```text
alice.smith@enterprise.org
415-555-1234
+1-800-555-0199
(800) 555-0199
```

If a match is found, `rails.co` returns:

```text
Request blocked: Personally Identifiable Information (PII) such as email addresses or phone numbers is not permitted.
```

The model is not called after this block.

### 6.2 Prompt-injection heuristics

`check_prompt_injection` uses regular expressions for phrases such as:

- `ignore all previous instructions`
- `disregard prior rules`
- `system prompt`
- `developer mode`
- `act as DAN`
- `bypass guardrails`

A detected request returns:

```text
Request blocked: Suspicious prompt injection pattern detected by safety heuristics.
```

The detector is intentionally fast and deterministic. It is not a complete semantic defense against every prompt-injection technique.

### 6.3 Defensive text extraction

The actions use `_extract_user_text` to safely obtain text from direct arguments, context fields such as `last_user_message`, and keyword arguments. Empty or invalid values return an empty string instead of raising an exception.

---

## 7. Portkey and provider routing

### Virtual-key mode

When `PORTKEY_CONFIG_ID` is empty, the application sends:

```http
x-portkey-api-key: <Portkey API key>
x-portkey-virtual-key: <Portkey virtual key>
```

This keeps provider access behind Portkey and avoids placing raw provider credentials in the application request code.

### Configuration-ID mode

When `PORTKEY_CONFIG_ID` is present, the application sends:

```http
x-portkey-api-key: <Portkey API key>
x-portkey-config: <Portkey configuration ID>
```

The external Portkey configuration may define provider fallback, Groq/Mistral selection, canary percentages, or other routing rules.

The repository description references Groq/Mistral failover and 70/30 canary routing. The checked-in Python code does not contain a local 70/30 algorithm or a direct Mistral SDK call. Those behaviors must be configured and managed by Portkey when a configuration ID is used.

### `app/gateway.py`

This module creates a Portkey SDK client. `get_portkey_client()` selects either configuration-ID mode or virtual-key mode. `test_gateway_connection()` performs a short direct Portkey chat-completion test with `max_tokens=64` and `temperature=0.0`.

The primary `/chat` path uses the NeMo/LangChain model connection, while the helper exists for a simple gateway connectivity check.

---

## 8. Output guardrails in detail

### 8.1 API-key detection

The output scanner recognizes patterns resembling:

- Groq keys beginning with `gsk_`
- OpenAI-style keys beginning with `sk-`
- Portkey-style keys beginning with `pk_`
- Bearer tokens

### 8.2 Private IP detection

The scanner detects RFC 1918 private addresses:

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`

For example:

```text
192.168.1.100
172.20.4.10
10.10.1.5
```

### 8.3 Confidential-term detection

The configured terms are:

```python
CONFIDENTIAL_TERMS = [
    "PROJECT_OMEGA",
    "CONFIDENTIAL_VAULT_PASS",
    "INTERNAL_DB_SECRET",
]
```

The scanner canonicalizes both the configured terms and generated output by removing non-alphanumeric characters and converting to uppercase. This catches evasion forms such as:

```text
P-R-O-J-E-C-T_O-M-E-G-A
P.R.O.J.E.C.T _ O.M.E.G.A
P ‑ R ‑ O ‑ J ‑ E ‑ C ‑ T
```

### 8.4 Blocking strategy

The active strategy is hard blocking. A detected leak returns:

```text
Response blocked: The generated response contained confidential system tokens or unauthorized internal data.
```

The unsafe generated output is not delivered to the client.

### 8.5 Redaction strategy

`redact_output_sensitive` also exists and can replace sensitive values with:

```text
[REDACTED_API_KEY]
[REDACTED_IP]
[REDACTED_PROJECT]
```

The redaction flow is present in `rails.co`, but `config.yml` activates hard blocking instead. Redaction is implemented and tested as an available alternative policy.

---

## 9. Timeout and error behavior

### Timeout

NeMo and the provider workflow are wrapped in:

```python
asyncio.wait_for(..., timeout=15.0)
```

If processing takes longer than 15 seconds, the endpoint returns HTTP `504 Gateway Timeout`.

### Upstream or processing failure

Unexpected errors are logged and converted to HTTP `502 Bad Gateway`. This gives clients a consistent category for provider, gateway, or guardrail failures.

### Validation failure

Invalid prompts are rejected by Pydantic with HTTP `422`.

### Rate-limit failure

Exceeded quotas return HTTP `429` with `Retry-After`.

---

## 10. Safe observability

The backend logs operational information including:

- Client identifier
- Request latency
- Prompt character count
- Model name
- Rate-limit events
- Timeout events
- Processing failures

The normal successful-request log does not include raw prompt text. This reduces the risk of logging PII or confidential content.

The endpoint also exposes:

```http
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
X-Response-Time-Ms
```

These headers allow clients and dashboards to observe quota and performance without requiring access to internal logs.

---

## 11. Health endpoint

`GET /health` returns the configured operational identity without calling the model:

```json
{
  "status": "healthy",
  "gateway": "portkey",
  "model": "openai/gpt-oss-120b"
}
```

The Streamlit frontend uses this endpoint to display whether the backend is available.

---

## 12. Streamlit frontend workflow

`frontend/app.py` is an interactive client, not a second model gateway. It communicates with FastAPI over HTTP.

It provides:

- Chat input and chat history
- Backend health status
- Latency telemetry
- Rate-limit quota telemetry
- Safe-query preset
- Input-email preset
- Input-phone preset
- Jailbreak preset
- Private-IP output preset
- Clear-history button
- Cloud cold-start handling

The frontend reads `BACKEND_URL`, defaulting to `http://127.0.0.1:8000`.

When the URL contains `onrender.com`, it assumes the backend may be sleeping on a free hosting tier. It then uses longer frontend timeouts and provides a wake-up button.

The frontend maps backend responses as follows:

| Backend result | Frontend behavior |
|---|---|
| `200` | Displays response and latency. |
| `422` | Displays empty/oversized prompt validation message. |
| `429` | Displays quota and retry message. |
| `504` | Displays upstream timeout message. |
| Other status | Displays gateway error. |
| Connection timeout in cloud | Explains possible cold start. |

Streamlit stores messages and latest telemetry in `st.session_state`.

---

## 13. NeMo Guardrails configuration

### `config.yml`

The YAML file defines:

- The OpenAI-compatible model engine
- Portkey base URL
- Portkey authentication headers
- The `noop` embedding provider
- General assistant instructions
- Input rail bindings
- Output rail bindings

The general instruction is:

```text
You are a helpful, concise AI assistant running inside the Guardrail Gateway Playground.
Always respond accurately, concisely, and professionally.
```

### `rails.co`

The Colang file contains refusal messages and flows:

- `check input pii`
- `check input injection`
- `redact sensitive output`
- `block sensitive output`

Flows call Python actions by name and can stop the dialogue with a refusal.

### `config/config.py`

The `NoopEmbeddingsIndex` registers a lightweight in-memory embedding provider. It avoids model downloads and does not perform real semantic search. This helps cloud startup and avoids unnecessary Hugging Face/ONNX costs, but it means the project’s demonstrated safety behavior is based on explicit deterministic flows rather than embedding retrieval.

---

## 14. Automated testing

The suite is designed to run offline and avoid real API spending.

`tests/conftest.py` provides:

- A FastAPI `TestClient`
- An automatic fixture that clears rate-limit history before and after each test

`tests/test_gateway.py` verifies:

1. Health endpoint returns HTTP 200.
2. Successful chat returns a mocked model response.
3. Latency and rate-limit headers are present.
4. Empty prompts receive HTTP 422.
5. Prompts over 4,000 characters receive HTTP 422.
6. Five requests pass and the sixth is rejected with HTTP 429.
7. Timeout errors become HTTP 504.
8. Provider errors become HTTP 502.
9. Emails and phone numbers are detected.
10. Prompt-injection phrases are detected.
11. API keys and private IPs are detected in output.
12. Confidential terms are detected.
13. Punctuation and Unicode spacing evasion is detected.
14. Sensitive output is correctly redacted by the alternative action.

Run the tests with:

```bash
pytest -v
```

The tests patch `app.main.rails.generate_async` with `AsyncMock`, so they verify application behavior without calling a real model provider.

---

## 15. Configuration and secrets

Copy the template:

```bash
cp .env.example .env
```

The required values are:

```env
PORTKEY_API_KEY=your_portkey_api_key_here
PORTKEY_VIRTUAL_KEY=your_virtual_key_here
```

Optional values:

```env
PORTKEY_CONFIG_ID=pc-your-fallback-config-slug
GROQ_MODEL=openai/gpt-oss-120b
```

`app/config.py` loads the values with `python-dotenv`, strips whitespace, checks required settings, and creates an immutable `Settings` object. The application raises a startup-time `ValueError` when required values are missing or still contain placeholder values.

Secrets should never be committed to Git. Only `.env.example` belongs in the repository.

---

## 16. Installation and execution

### Prerequisites

- Python 3.10 or 3.11
- Portkey account
- Portkey API key
- Portkey virtual key or configuration ID
- Access to the configured upstream model/provider

### Install

```bash
git clone https://github.com/Amankhan1009/guardrail-gateway.git
cd guardrail-gateway

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env with real Portkey settings
```

### Start FastAPI

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Useful URLs:

```text
Swagger UI: http://127.0.0.1:8000/docs
Health:      http://127.0.0.1:8000/health
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Explain AI guardrails in one sentence."}'
```

### Start Streamlit

In another terminal:

```bash
source venv/bin/activate
streamlit run frontend/app.py
```

Open:

```text
http://localhost:8501
```

For a remote backend:

```bash
BACKEND_URL=https://your-backend.example.com streamlit run frontend/app.py
```

---

## 17. Real-world value

### Customer support

The gateway can protect a public customer-support bot from common jailbreaks and accidental structured PII submissions while exposing latency and quota information to operators.

### Internal enterprise assistants

An assistant connected to internal systems may accidentally reveal internal addresses, API keys, or project names. Output inspection provides a final egress control before the response reaches the user.

### Privacy-sensitive systems

Input checks can prevent common emails and phone numbers from being forwarded to the model provider. A production deployment would expand this with entity recognition and organization-specific policies.

### Provider resilience

Portkey can centralize model-provider credentials and support routing, fallback, and model changes without requiring the application to implement every provider separately.

### Cost and abuse control

Input rails can reject known unsafe prompts before provider execution, and the sliding-window limiter limits repeated calls from a client. This reduces unnecessary model spend and protects the service from basic abuse.

### SRE and operations

Health checks, timeouts, standardized HTTP errors, latency headers, and rate-limit headers make the model dependency behave more like a managed service.

### Security education

The Streamlit presets provide an immediate demonstration of safe requests, PII interception, jailbreak interception, output inspection, and quota behavior.

---

## 18. Strengths

- Clear separation between frontend, API, policy, guardrail, provider, and test layers.
- Strict request validation at the HTTP border.
- Fast deterministic input interception.
- Output leakage detection with canonical anti-evasion normalization.
- Optional redaction in addition to hard blocking.
- Provider credentials abstracted behind Portkey.
- Timeout enforcement prevents indefinite requests.
- Rate-limit headers make quota visible to clients.
- Raw prompt text is not logged in the normal success path.
- Tests are hermetic and do not spend provider tokens.
- Streamlit makes the architecture easy to demonstrate.
- The README explicitly documents the gap between the playground and production architecture.

---

## 19. Limitations and production improvements

The project is a strong playground, but the following changes would be appropriate before using it as a production enterprise gateway:

1. Replace the in-memory limiter with Redis or another distributed store.
2. Add authentication and authorization to `/chat`.
3. Add tenant-aware quotas and identity-based rate limiting.
4. Add request IDs and correlation IDs.
5. Add OpenTelemetry traces across UI, API, guardrails, Portkey, and provider.
6. Use structured JSON logs and centralized log redaction.
7. Avoid returning raw exception text to external clients.
8. Add provider retries, circuit breakers, and backoff policies.
9. Add integration tests for real Portkey routing and fallback.
10. Verify and test the external Groq/Mistral routing configuration.
11. Add explicit tests for any 70/30 canary behavior.
12. Expand PII recognition beyond emails and phone numbers.
13. Add semantic prompt-injection detection.
14. Add content-safety and abuse classifiers.
15. Add more API-key and token formats.
16. Add stronger output policy classification.
17. Add secret management through a managed vault.
18. Add production readiness/liveness probes.
19. Add load, concurrency, and multi-worker tests.
20. Add policy versioning and rollback.
21. Add TLS, deployment hardening, and secure headers.
22. Add model cost and token-budget enforcement.
23. Add audit storage with privacy and retention controls.
24. Add input/output size limits appropriate to the selected model.
25. Add tests for cancellation and partial upstream failures.

### Specific implementation realities

- The rate limiter is process-local.
- PII detection is limited to email and phone patterns.
- Injection detection is keyword/regex based.
- Output inspection is deterministic and only knows configured patterns.
- The no-op embedding provider does not perform semantic embedding search.
- Local Python code does not implement a 70/30 canary algorithm.
- Local Python code does not directly call a Mistral SDK; provider fallback must be configured in Portkey.

---

## 20. Simple explanation for a presentation

> This project is a secure LLM gateway built with FastAPI. Users do not call the model provider directly. Every request first passes through schema validation, rate limiting, and NVIDIA NeMo Guardrails. The gateway blocks common PII such as emails and phone numbers and detects common prompt-injection phrases before sending safe requests to the model through Portkey. When the model responds, the output is inspected for API keys, private IP addresses, and confidential project terms. Sensitive output can be blocked or redacted. The API also enforces a 15-second timeout, provides health and telemetry information, and avoids logging raw prompt text. A Streamlit dashboard demonstrates the complete workflow, and Pytest verifies the behavior offline using mocked model responses.

---

## 21. One-request sequence diagram

```text
Client / Streamlit
      |
      | POST /chat {prompt}
      v
FastAPI + Pydantic
      |
      | Reject empty or >4000-character prompt
      v
Rate limiter
      |
      | Reject after 5 requests / 60 seconds
      v
NeMo input rail: PII
      |
      | Reject email/phone
      v
NeMo input rail: injection
      |
      | Reject common jailbreak phrases
      v
Portkey gateway
      |
      | Virtual key or configuration ID
      v
Groq / configured upstream model
      |
      | Generated response
      v
NeMo output rail
      |
      | Detect API keys, private IPs, confidential terms
      | Block or redact
      v
FastAPI response
      |
      | JSON + latency + rate-limit headers
      v
Client / Streamlit
```

---

## 22. Final summary

`guardrail-gateway` demonstrates the complete control plane around an LLM request. It does not merely call a model; it validates requests, limits abuse, applies input safety rules, routes through a provider gateway, enforces an upstream timeout, inspects generated output, protects operational logs, and exposes telemetry to clients.

Its strongest value is architectural: it shows where safety and reliability controls belong in an LLM application. The repository is suitable for learning, demonstrations, prototypes, interviews, and as a foundation for a production gateway. Before production use, distributed state, authentication, stronger semantic safety models, comprehensive PII detection, real observability, and thoroughly tested provider failover should be added.
