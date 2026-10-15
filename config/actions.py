"""
Custom NeMo Guardrail Actions.
Implements data-driven, canonicalized input and output scanners.
"""

import re
from nemoguardrails.actions import action

# ==============================================================================
# 1. INPUT RAIL CONFIGURATION & PATTERNS
# ==============================================================================

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    re.IGNORECASE,
)

PHONE_REGEX = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior\s+)?rules", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+mode", re.IGNORECASE),
    re.compile(r"act\s+as\s+dan", re.IGNORECASE),
    re.compile(r"bypass\s+guardrails?", re.IGNORECASE),
]

# ==============================================================================
# 2. OUTPUT RAIL CONFIGURATION & DATA-DRIVEN TERMS
# ==============================================================================

API_KEY_REGEX = re.compile(
    r"(?:gsk_[a-zA-Z0-9]{20,}|sk-[a-zA-Z0-9]{20,}|pk_[a-zA-Z0-9]{20,}|Bearer\s+[a-zA-Z0-9_\-\.]{20,})"
)

INTERNAL_IP_REGEX = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"
)

# Configurable list of proprietary terms (easy to extend)
CONFIDENTIAL_TERMS = [
    "PROJECT_OMEGA",
    "CONFIDENTIAL_VAULT_PASS",
    "INTERNAL_DB_SECRET",
]

# Automatically pre-compute canonical alphanumeric versions at module load time
# e.g., "PROJECT_OMEGA" -> "PROJECTOMEGA"
CANONICAL_CONFIDENTIAL_TERMS = {
    re.sub(r"[^A-Za-z0-9]", "", term).upper()
    for term in CONFIDENTIAL_TERMS
}


def _extract_user_text(text: str = None, context: dict = None, kwargs: dict = None) -> str:
    """
    Defensively extracts text from arguments or context without throwing errors.
    """
    if isinstance(text, str) and text.strip():
        return text.strip()

    if context and isinstance(context, dict):
        for key in ["last_user_message", "user_message", "bot_message", "text"]:
            val = context.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    if kwargs and isinstance(kwargs, dict):
        for val in kwargs.values():
            if isinstance(val, str) and val.strip():
                return val.strip()

    return ""


# ==============================================================================
# INPUT ACTIONS
# ==============================================================================

@action(name="check_input_pii")
async def check_input_pii(text: str = None, context: dict = None, **kwargs) -> bool:
    user_text = _extract_user_text(text=text, context=context, kwargs=kwargs)
    if not user_text:
        return False
    return bool(EMAIL_REGEX.search(user_text) or PHONE_REGEX.search(user_text))


@action(name="check_prompt_injection")
async def check_prompt_injection(text: str = None, context: dict = None, **kwargs) -> bool:
    user_text = _extract_user_text(text=text, context=context, kwargs=kwargs)
    if not user_text:
        return False
    return any(p.search(user_text) for p in INJECTION_PATTERNS)


# ==============================================================================
# OUTPUT ACTIONS
# ==============================================================================

@action(name="check_output_leakage")
async def check_output_leakage(text: str = None, context: dict = None, **kwargs) -> bool:
    """
    Data-driven output scanner:
    1. Checks for API keys and private IPs via regex.
    2. Runs canonical anti-evasion across ALL configured confidential terms.
    """
    bot_text = _extract_user_text(text=text, context=context, kwargs=kwargs)
    if not bot_text:
        return False

    # 1. API Keys and Private IPs
    if API_KEY_REGEX.search(bot_text) or INTERNAL_IP_REGEX.search(bot_text):
        return True

    # 2. Universal Canonicalization: strip all non-alphanumeric characters
    # Catches: P-R-O-J-E-C-T, P.R.O.J.E.C.T, P_R_O_J_E_C_T, or P ‑ R ‑ O...
    collapsed = re.sub(r"[^A-Za-z0-9]", "", bot_text).upper()

    # Check if ANY of our configured confidential terms exist in the collapsed stream
    return any(term in collapsed for term in CANONICAL_CONFIDENTIAL_TERMS)


@action(name="redact_output_sensitive")
async def redact_output_sensitive(text: str = None, context: dict = None, **kwargs) -> str:
    """
    Scans the generated bot response and masks sensitive tokens with '[REDACTED]'.
    """
    bot_text = _extract_user_text(text=text, context=context, kwargs=kwargs)
    if not bot_text:
        return ""

    sanitized = bot_text

    # Mask API keys and IPs
    sanitized = API_KEY_REGEX.sub("[REDACTED_API_KEY]", sanitized)
    sanitized = INTERNAL_IP_REGEX.sub("[REDACTED_IP]", sanitized)

    # Mask any configured confidential terms dynamically
    for term in CONFIDENTIAL_TERMS:
        # Dynamically build a regex that allows optional non-alphanumerics between letters
        pattern = r"[^A-Za-z0-9]*".join(list(re.sub(r"[^A-Za-z0-9]", "", term)))
        sanitized = re.sub(pattern, "[REDACTED_PROJECT]", sanitized, flags=re.IGNORECASE)

    return sanitized