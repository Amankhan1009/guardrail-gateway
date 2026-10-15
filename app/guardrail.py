"""
Guardrail Engine Bridge.
Initializes NeMo Guardrails wired to route through the Portkey AI Gateway.
"""

from pathlib import Path
from langchain_openai import ChatOpenAI
from nemoguardrails import LLMRails, RailsConfig

from app.config import settings


def get_rails_instance() -> LLMRails:
    """
    Builds and returns an LLMRails instance with a custom ChatOpenAI model
    configured to route through the Portkey Gateway.
    """
    # 1. Path to the NeMo configuration folder
    config_path = Path(__file__).parent.parent / "config"
    config = RailsConfig.from_path(str(config_path))

    # 2. Configure LangChain's ChatOpenAI client pointing to Portkey
    # This guarantees that we use /v1/chat/completions (not legacy /v1/completions)
    chat_model = ChatOpenAI(
        model=settings.groq_model,
        base_url=settings.portkey_gateway_url,
        api_key=settings.portkey_api_key,
        default_headers={
            "x-portkey-api-key": settings.portkey_api_key,
            "x-portkey-virtual-key": settings.portkey_virtual_key,
        },
        temperature=0.0,
        max_tokens=256,
    )

    # 3. Instantiate NeMo Guardrails with our custom chat client
    return LLMRails(config=config, llm=chat_model)


# Singleton guardrail rails instance
rails = get_rails_instance()