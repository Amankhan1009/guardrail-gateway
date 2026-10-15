"""
Guardrail Engine Bridge.
Initializes NeMo Guardrails wired to route through the Portkey AI Gateway
with dynamic cross-provider fallback (Groq -> Mistral).
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

    # 2. Build Portkey routing headers
    # If a Portkey Config ID is set, Portkey manages multi-provider failover
    headers = {
        "x-portkey-api-key": settings.portkey_api_key,
    }
    if settings.portkey_config_id:
        headers["x-portkey-config"] = settings.portkey_config_id
    else:
        headers["x-portkey-virtual-key"] = settings.portkey_virtual_key

    # 3. Configure LangChain's ChatOpenAI client pointing to Portkey Gateway
    chat_model = ChatOpenAI(
        model=settings.groq_model,
        base_url=settings.portkey_gateway_url,
        api_key=settings.portkey_api_key,
        default_headers=headers,
        temperature=0.0,
        max_tokens=256,
    )

    # 4. Instantiate NeMo Guardrails with our custom chat client
    return LLMRails(config=config, llm=chat_model)


# Singleton guardrail rails instance
rails = get_rails_instance()