"""
Application configuration and environment variable management.
Loads and validates credentials required for Portkey and Groq.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env into os.environ
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """
    Immutable application settings container.
    """
    portkey_api_key: str
    portkey_virtual_key: str
    groq_model: str
    portkey_gateway_url: str = "https://api.portkey.ai/v1"


def load_settings() -> Settings:
    """
    Loads and validates required environment variables.
    """
    portkey_api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    portkey_virtual_key = os.getenv("PORTKEY_VIRTUAL_KEY", "").strip()
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()

    missing = []
    if not portkey_api_key or portkey_api_key == "your_portkey_api_key_here":
        missing.append("PORTKEY_API_KEY")
    if not portkey_virtual_key or portkey_virtual_key == "paste_your_copied_slug_here":
        missing.append("PORTKEY_VIRTUAL_KEY")

    if missing:
        raise ValueError(
            f"Configuration Error: Missing required setting: {', '.join(missing)}. "
            "Please check your .env file."
        )

    return Settings(
        portkey_api_key=portkey_api_key,
        portkey_virtual_key=portkey_virtual_key,
        groq_model=groq_model,
    )


# Singleton instance created when module is imported
settings = load_settings()