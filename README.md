# 🛡️ Guardrail Gateway Playground

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![NeMo Guardrails](https://img.shields.io/badge/NVIDIA-NeMo%20Guardrails-76B900.svg?logo=nvidia&logoColor=white)](https://github.com/NVIDIA/NeMo-Guardrails)
[![Portkey AI Gateway](https://img.shields.io/badge/Portkey-AI%20Gateway-FF5722.svg)](https://portkey.ai)
[![Groq](https://img.shields.io/badge/Groq-LPU%20Inference-f55036.svg)](https://groq.com)
[![Tests](https://img.shields.io/badge/Tests-11%20Passed%20(0.03s)-success.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An educational, decoupled **AI Guardrail & LLM Gateway Playground** engineered from the ground up to explore conversational safety, enterprise policy enforcement, data loss prevention (DLP), and low-latency reverse proxying.

---

## 📐 Architecture Overview

The system strictly decouples the client interface, API gateway, safety policies, and upstream inference providers:

```
                           [ CLIENT REQUEST ]
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 1. HTTP BORDER (FastAPI & Pydantic)                                   │
│    • Inbound Schema Validation (Rust-backed pydantic-core)             │
│    • Rejects empty strings ("") or oversized inputs (>4000 chars)     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. GATEWAY POLICIES (app/policies/rate_limiter.py)                     │
│    • Sliding-Window rate limiting (5 req / 60s per client IP)          │
│    • Over quota? ──> Rejects with HTTP 429 + Retry-After               │
│    • Monotonic microsecond latency timer (time.perf_counter)           │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. INPUT GUARDRAILS (config/actions.py & config/rails.co)              │
│    • Regex Scanners: PII detection (emails, international phone nums)  │
│    • Heuristic Scanners: Prompt injection keyword detection           │
│    • Colang Dialogue Machine: Semantic intent matching (MiniLM)        │
│    • Violation detected? ──> Refuses immediately in < 12ms! ($0 spent) │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ (Only if all Input Rails pass)
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. AI GATEWAY (Portkey & app/gateway.py)                               │
│    • Authenticated via Portkey Virtual Key (Zero raw secrets in code)  │
│    • Request timeout enforcement (asyncio.wait_for, 15s) ──> HTTP 504  │
│    • Streams token usage & latency metrics to Portkey Cloud Dashboard  │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 5. UPSTREAM INFERENCE (Groq LPU Engine)                                │
│    • Ultra-fast inference via hosted openai/gpt-oss-120b               │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 6. OUTPUT GUARDRAILS (config/actions.py & config/rails.co)             │
│    • Egress Data Loss Prevention (DLP) on generated $bot_message       │
│    • Alphanumeric Canonicalization: Anti-evasion against hyphens/dots  │
│    • Detects private RFC 1918 IPs, API keys, and secret project names  │
│    • Configurable Strategy A (Redaction): In-place masking with tags   │
│    • Configurable Strategy B (Blocking): Drops output with refusal     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 7. SAFE OBSERVABILITY & CLIENT DELIVERY                                │
│    • OWASP LLM06 Safe Logging: Logs metrics, NEVER raw prompt text     │
│    • Injects X-RateLimit-* and X-Response-Time-Ms headers              │
│    • Returns structured JSON ChatResponse (HTTP 200 OK)                │
└────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Features

* **Sub-12ms Local Interception:** Malicious injections and PII prompts are resolved locally on the CPU in under 12 milliseconds, consuming **0 Groq tokens** and costing **$0.00**.
* **Enterprise Credential Vaulting:** Employs Portkey Virtual Keys—application code never touches or transmits raw Groq API keys.
* **Anti-Evasion Canonicalization:** Universal alphanumeric normalization strips whitespace, non-breaking Unicode hyphens (`\u2011`), and punctuation, neutralizing character-spacing evasion tricks (e.g. `P‑R‑O‑J‑E‑C‑T _ O‑M‑E‑G‑A`).
* **Configurable Egress DLP:** Switch between **Strategy A (In-Place Redaction)** and **Strategy B (Hard Blocking)** via declarative YAML configuration.
* **Sliding-Window Rate Limiting:** Smooth sliding-window algorithm prevents boundary burst spikes; returns standard `Retry-After` headers.
* **OWASP LLM06 Safe Observability:** Strict logging standards record duration, token usage, and prompt character lengths, but strictly omit raw prompt text to prevent PII leakage into disk logs.
* **Hermetic Zero-Cost Test Suite:** 11 comprehensive automated tests running in **0.03 seconds** using in-memory mock adapters ($0 test overhead).
* **Decoupled Streamlit Web UI:** Interactive dashboard featuring live latency meters, quota trackers, and one-click guardrail attack presets.

---

## 📂 Project Structure

```text
guardrail-gateway/
├── .env.example              # Documented environment variable template
├── .gitignore                # Protects secrets, cache, and virtual environments
├── requirements.txt          # Synchronized, pinned dependencies
├── README.md                 # System architecture and documentation
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI entrypoint, policies, and routes
│   ├── config.py             # Fail-fast environment variable validation
│   ├── schemas.py            # Pydantic request & response contracts
│   ├── gateway.py            # Portkey AI Gateway client adapter
│   ├── guardrail.py          # NeMo Guardrails Python bridge
│   └── policies/
│       ├── __init__.py
│       └── rate_limiter.py   # In-memory sliding-window rate limiter
├── config/                   # NeMo Guardrails configuration bundle
│   ├── config.yml            # Pipeline bindings, instructions & models
│   ├── rails.co              # Colang safety flows & user intents
│   └── actions.py            # Deterministic Python input/output scanners
├── frontend/
│   └── app.py                # Streamlit interactive web console
└── tests/
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures and state-clearing helpers
    └── test_gateway.py       # 11 hermetic unit & integration tests
```

---

## 🚀 Quickstart

### 1. Prerequisites
* Python 3.10 or 3.11
* A free [Groq API Key](https://console.groq.com/keys)
* A free [Portkey Account](https://app.portkey.ai/)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/guardrail-gateway.git
cd guardrail-gateway

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install synchronized dependencies
pip install -r requirements.txt
```

### 3. Configure Secrets
Create a Virtual Key in your Portkey Dashboard (under **LLM Integrations**) targeting Groq.
```bash
cp .env.example .env
```
Edit `.env` with your real keys:
```env
PORTKEY_API_KEY=pk_live_...
PORTKEY_VIRTUAL_KEY=groq-gateway-...
GROQ_MODEL=openai/gpt-oss-120b
```

---

## 🖥️ Running the Application

### Start the FastAPI Backend
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
* **Interactive Swagger UI:** Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **Health Check:** `curl http://127.0.0.1:8000/health`

### Start the Streamlit Frontend
In a second terminal window:
```bash
source venv/bin/activate
streamlit run frontend/app.py
```
Visit [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🧪 Running Automated Tests

Run the full automated test suite (runs 100% offline with $0 API spend):
```bash
pytest -v
```

```text
tests/test_gateway.py::test_health_check PASSED                              [  9%]
tests/test_gateway.py::test_chat_success_mocked PASSED                       [ 18%]
tests/test_gateway.py::test_empty_prompt_rejected PASSED                     [ 27%]
tests/test_gateway.py::test_oversized_prompt_rejected PASSED                 [ 36%]
tests/test_gateway.py::test_rate_limiting_enforced PASSED                    [ 45%]
tests/test_gateway.py::test_gateway_timeout_mapped_to_504 PASSED             [ 54%]
tests/test_gateway.py::test_upstream_failure_mapped_to_502 PASSED            [ 63%]
tests/test_gateway.py::test_input_pii_detection PASSED                       [ 72%]
tests/test_gateway.py::test_input_injection_heuristics PASSED               [ 81%]
tests/test_gateway.py::test_output_leakage_and_canonical_anti_evasion PASSED [ 90%]
tests/test_gateway.py::test_output_redaction_transformation PASSED            [100%]

======================= 11 passed in 0.03s =======================
```

---

## 📊 Architectural Gap Analysis: Playground vs. Production

| Concern | Playground Implementation | Enterprise Production Pattern | Rationale |
| :--- | :--- | :--- | :--- |
| **Rate Limiter** | In-Memory `collections.deque` | **Distributed Redis Cluster** (Token Bucket via Lua) | In-memory state is lost on server restart and isolated across multi-worker processes (`uvicorn --workers 4`). |
| **PII Detection** | Pre-compiled Regular Expressions | **Microsoft Presidio** + NLP NER Models | Regex reliably detects structured PII (emails/phones), but misses unstructured PII (names, physical addresses). |
| **Anti-Evasion** | Alphanumeric Normalization | **LLM-as-a-Judge / Llama Guard 3** | Regex canonicalization stops punctuation tricks, but an LLM judge evaluates semantic intent, ciphers, and foreign languages. |
| **Observability** | Python standard `logging` | **OpenTelemetry (OTel) Distributed Traces** | OTel tracks end-to-end spans from client UI -> API gateway -> Guardrail -> Portkey -> Groq with distributed trace IDs. |

---

## 📜 License
This project is open-source and available under the [MIT License](LICENSE).