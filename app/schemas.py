"""
Pydantic data schemas for API request and response contracts.
Defines strict validation rules and observability metadata.
"""

from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """
    Inbound request payload contract for POST /chat.
    """
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The user input prompt to process through guardrails and the gateway.",
        examples=["Explain what an AI guardrail is in one sentence."]
    )


class ChatResponse(BaseModel):
    """
    Outbound response payload contract returned to the client.
    Includes generated text, provider metadata, and round-trip latency.
    """
    response: str = Field(
        ...,
        description="The generated completion after passing guardrail safety checks."
    )
    model: str = Field(
        ...,
        description="The model identifier that processed the completion."
    )
    gateway: str = Field(
        default="portkey",
        description="The LLM gateway through which the call was routed."
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Total round-trip processing duration in milliseconds."
    )