"""
Main FastAPI application entrypoint.
Orchestrates Rate Limiting, Request Timeouts, Safe Observability,
NeMo Guardrails, and Portkey Gateway routing.
"""

import asyncio
import logging
import time
from fastapi import FastAPI, HTTPException, Request, Response, status

from app.config import settings
from app.guardrail import rails
from app.policies.rate_limiter import rate_limiter
from app.schemas import ChatRequest, ChatResponse

# Configure structured, secure logging
# Notice: Format excludes prompt contents to prevent PII leakage into log sinks
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [gateway] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("guardrail-gateway")

app = FastAPI(
    title="Guardrail Gateway Playground",
    description="Learning playground for LLM Gateways (Portkey) and AI Guardrails (NeMo).",
    version="1.0.0",
)


@app.get("/health", tags=["Operations"])
async def health_check():
    """
    Operational health check to verify server status and active configurations.
    """
    return {
        "status": "healthy",
        "gateway": "portkey",
        "model": settings.groq_model,
    }


@app.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    tags=["Guardrail Gateway"],
)
async def chat_endpoint(
    body: ChatRequest,
    request: Request,
    response: Response,
):
    """
    Primary chat endpoint:
    1. Enforces per-client sliding-window rate limiting.
    2. Applies a 15-second request timeout to prevent hanging connections.
    3. Executes NeMo Guardrails (Input & Output rails).
    4. Routes model generation through Portkey Gateway to Groq.
    5. Measures latency and logs safe audit metadata.
    """
    # 1. Identify client IP for rate limiting
    client_ip = request.client.host if request.client else "127.0.0.1"

    # 2. Evaluate Rate Limiting Policy (5 req / 60s)
    rate_res = rate_limiter.check(client_ip)

    # Attach standard rate-limit headers to the response
    response.headers["X-RateLimit-Limit"] = str(rate_res.limit)
    response.headers["X-RateLimit-Remaining"] = str(rate_res.remaining)
    response.headers["X-RateLimit-Reset"] = str(rate_res.reset_after)

    if not rate_res.allowed:
        logger.warning(
            "Rate limit exceeded: client=%s, reset_after=%.2fs",
            client_ip,
            rate_res.reset_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {rate_res.reset_after} seconds.",
            headers={"Retry-After": str(int(rate_res.reset_after))},
        )

    # 3. Start high-resolution monotonic timer for latency tracking
    start_time = time.perf_counter()

    try:
        # 4. Enforce 15-second timeout on NeMo / Portkey / Groq execution
        result = await asyncio.wait_for(
            rails.generate_async(
                messages=[{"role": "user", "content": body.prompt}]
            ),
            timeout=15.0,
        )

        # Calculate round-trip duration in milliseconds
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response_text = result.get("content", "").strip()

        # 5. Safe Observability Logging: Log metrics, NEVER log prompt text!
        logger.info(
            "Request completed: client=%s, latency_ms=%.2f, prompt_chars=%d, model=%s",
            client_ip,
            latency_ms,
            len(body.prompt),
            settings.groq_model,
        )

        # Inject latency header into HTTP response
        response.headers["X-Response-Time-Ms"] = str(latency_ms)

        return ChatResponse(
            response=response_text,
            model=settings.groq_model,
            gateway="portkey",
            latency_ms=latency_ms,
        )

    except asyncio.TimeoutError as e:
        logger.error("Request timed out: client=%s, timeout=15s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Gateway Timeout: Upstream model provider took longer than 15 seconds to respond.",
        ) from e

    except Exception as e:
        logger.error("Processing failure: client=%s, error=%s", client_ip, str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gateway/Guardrail processing error: {str(e)}",
        ) from e