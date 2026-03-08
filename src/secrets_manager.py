"""Secret detection, redaction, and OS keychain integration."""

import re
from typing import Dict, Optional, Tuple

import keyring

KEYRING_SERVICE = "apc"

SECRET_FIELD_PATTERNS = [
    r".*token.*",
    r".*secret.*",
    r".*password.*",
    r".*api_?key.*",
    r".*auth.*key.*",
    r".*credential.*",
    r".*private.*key.*",
]

# Regex for values that look like secrets (high-entropy, common token formats)
_SECRET_VALUE_RE = re.compile(
    r"(?:"
    r"sk-[A-Za-z0-9]{20,}"  # OpenAI-style keys
    r"|sk-ant-[A-Za-z0-9\-]{20,}"  # Anthropic-style keys
    r"|AIza[A-Za-z0-9_\-]{35,}"  # Google API keys
    r"|eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"  # JWT tokens
    r"|ghp_[A-Za-z0-9]{36,}"  # GitHub personal tokens
    r"|ghs_[A-Za-z0-9]{36,}"  # GitHub server tokens
    r"|[A-Za-z0-9+/]{40,}={0,2}"  # Base64-encoded blobs (≥40 chars)
    r")"
)


def scrub_content(text: str) -> str:
    """Replace recognisable secret values in *text* with a redaction marker.

    This is a best-effort scan for common token / API-key formats.
    It does NOT guarantee all secrets are removed — use it as a defence-in-depth
    layer for export output that might be shared or committed to version control.
    """
    return _SECRET_VALUE_RE.sub("[REDACTED]", text)


def is_secret_field(field_name: str) -> bool:
    """Check if a field name looks like it contains a secret."""
    return any(re.match(p, field_name.lower()) for p in SECRET_FIELD_PATTERNS)


def detect_and_redact(env_vars: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Split env vars into redacted (with ${PLACEHOLDER}) and secrets.

    Returns:
        (redacted_env, secrets_dict)
    """
    redacted = {}
    secrets = {}
    for k, v in env_vars.items():
        if is_secret_field(k) and v and not v.startswith("${"):
            redacted[k] = f"${{{k}}}"
            secrets[k] = v
        else:
            redacted[k] = v
    return redacted, secrets


def store_secret(user_id: str, name: str, value: str) -> None:
    """Store a secret in the OS keychain."""
    keyring.set_password(KEYRING_SERVICE, f"{user_id}/{name}", value)


def retrieve_secret(user_id: str, name: str) -> Optional[str]:
    """Retrieve a secret from the OS keychain."""
    return keyring.get_password(KEYRING_SERVICE, f"{user_id}/{name}")


def store_secrets_batch(user_id: str, secrets: Dict[str, str]) -> None:
    """Store multiple secrets in the OS keychain."""
    for name, value in secrets.items():
        store_secret(user_id, name, value)


def resolve_placeholders(
    env_vars: Dict[str, str], placeholders: list, user_id: str
) -> Tuple[Dict[str, str], list]:
    """Resolve ${PLACEHOLDER} values from keychain.

    Returns:
        (resolved_env, missing_keys)
    """
    resolved = env_vars.copy()
    missing = []
    for key in placeholders:
        if key in resolved and resolved[key].startswith("${"):
            value = retrieve_secret(user_id, key)
            if value:
                resolved[key] = value
            else:
                missing.append(key)
    return resolved, missing
