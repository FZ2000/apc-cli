"""Thin HTTP client for LLM API calls.

Supports three calling modes:
- anthropic-messages: Anthropic Messages API (x-api-key auth)
- openai-completions: OpenAI-compatible Chat Completions
  (covers OpenAI, Qwen, GLM, MiniMax, Kimi, Gemini OpenAI-compat)
- claude-cli: Shell out to `claude -p` for OAuth/setup-token users

Uses httpx (already a project dependency).

Security note: base_url is validated before use to prevent config-injection
redirects (analogous to CVE-2026-21852 in Claude Code). apc-cli deliberately
does NOT read ANTHROPIC_BASE_URL from the environment — base URLs come from
the hardcoded PROVIDERS registry or the user's ~/.apc/models.json, validated
here before any HTTP call.
"""

import json
import os
import shutil
import subprocess
from typing import Optional
from urllib.parse import urlparse

import httpx

from llm_config import (
    PROVIDERS,
    resolve_api_key,
    resolve_auth_type,
    resolve_model,
)

# Timeout: 30s connect, 120s read (LLM responses can be slow)
_TIMEOUT = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)

# Known cloud provider hostnames. Custom/local providers are exempt from
# HTTPS enforcement (e.g. http://127.0.0.1:11434 for Ollama is fine).
_CLOUD_HOSTS = {
    "api.anthropic.com",
    "api.openai.com",
    "generativelanguage.googleapis.com",
    "dashscope.aliyuncs.com",
    "open.bigmodel.cn",
    "api.minimax.chat",
    "api.moonshot.cn",
}


def _validate_base_url(base_url: str) -> None:
    """Validate base_url before use to prevent config-injection redirects.

    Rules:
    - Must be a non-empty string
    - Must have http or https scheme
    - No user-info component (no credentials embedded in URL)
    - Known cloud provider endpoints must use HTTPS (not HTTP)
    - Rejects obviously malformed values (path traversal, whitespace, etc.)

    Raises LLMError for invalid values.
    """
    if not base_url or not isinstance(base_url, str):
        raise LLMError("LLM base_url is empty or invalid")

    stripped = base_url.strip()
    if stripped != base_url:
        raise LLMError(f"LLM base_url contains leading/trailing whitespace: {base_url!r}")

    try:
        parsed = urlparse(base_url)
    except Exception as exc:
        raise LLMError(f"LLM base_url could not be parsed: {base_url!r}") from exc

    if parsed.scheme not in ("http", "https"):
        raise LLMError(
            f"LLM base_url has unsupported scheme {parsed.scheme!r} (must be http or https): "
            f"{base_url!r}"
        )

    if parsed.username or parsed.password:
        raise LLMError("LLM base_url must not contain embedded credentials (user:pass@host)")

    # Cloud providers must use HTTPS to prevent plaintext key transmission
    hostname = (parsed.hostname or "").lower()
    if hostname in _CLOUD_HOSTS and parsed.scheme != "https":
        raise LLMError(
            f"Cloud provider endpoint {hostname!r} must use HTTPS, not HTTP: {base_url!r}"
        )


class LLMError(Exception):
    """Raised when an LLM API call fails."""

    pass


def call_llm(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    profile: Optional[str] = None,
) -> str:
    """Call the configured LLM and return the text response.

    Resolves model/profile from:
    1. Explicit model arg (e.g. "anthropic/claude-sonnet-4-6")
    2. Default model from ~/.apc/models.json
    3. Env var fallback per provider

    Args:
        prompt: The user message to send.
        system: Optional system message.
        model: Optional model override in "provider/model" format.
        profile: Optional auth profile key (e.g. "anthropic:work").

    Returns:
        The text content of the LLM response.

    Raises:
        LLMError: If the API call fails or no model is configured.
    """
    # Resolve model
    if model and "/" in model:
        provider, model_name = model.split("/", 1)
        pdef = PROVIDERS.get(provider)
        if not pdef:
            raise LLMError(f"Unknown provider: {provider}")
        base_url = pdef.base_url
        api_dialect = pdef.api_dialect
    else:
        resolved = resolve_model()
        if not resolved:
            raise LLMError("No LLM model configured. Run 'apc configure' to set up a provider.")
        provider = resolved["provider"]
        model_name = resolved["model"]
        base_url = resolved["base_url"]
        api_dialect = resolved["api_dialect"]

    # Resolve API key and auth type
    auth_type = resolve_auth_type(provider, profile)

    # For Anthropic token auth, use Claude CLI instead of direct API
    if provider == "anthropic" and auth_type == "token":
        return _call_claude_cli(model_name, prompt, system)

    api_key = resolve_api_key(provider, profile)
    if not api_key:
        raise LLMError(
            f"No API key found for provider '{provider}'. "
            f"Run 'apc configure' or set the environment variable."
        )

    _validate_base_url(base_url)

    if api_dialect == "anthropic-messages":
        return _call_anthropic(base_url, api_key, model_name, prompt, system)
    else:
        return _call_openai_compat(base_url, api_key, model_name, prompt, system)


def _call_claude_cli(
    model: str,
    prompt: str,
    system: str,
) -> str:
    """Call Claude via the Claude CLI (claude -p). Uses the CLI's own OAuth auth."""
    claude_path = shutil.which("claude")
    if not claude_path:
        raise LLMError(
            "Claude CLI not found. Install it or configure an API key instead:\n"
            "  apc configure --provider anthropic --api-key YOUR_KEY"
        )

    # Clean env: strip all Claude Code env vars to allow nested invocation
    _strip_vars = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"}
    env = {k: v for k, v in os.environ.items() if k not in _strip_vars}

    # Write prompt to a temp file to avoid OS arg length limits
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(prompt)
        prompt_file = f.name

    cmd = [
        claude_path,
        "--print",
        "--model",
        model,
        "--no-session-persistence",
        "--allowedTools",
        "",
    ]
    if system:
        cmd.extend(["--append-system-prompt", system])

    try:
        with open(prompt_file, "r", encoding="utf-8") as stdin_f:
            result = subprocess.run(
                cmd,
                stdin=stdin_f,
                capture_output=True,
                text=True,
                timeout=180,
                env=env,
            )
    except subprocess.TimeoutExpired:
        raise LLMError("Claude CLI call timed out after 180s")
    except FileNotFoundError:
        raise LLMError("Claude CLI not found in PATH")
    finally:
        try:
            os.unlink(prompt_file)
        except OSError:
            pass

    if result.returncode != 0:
        # Limit stderr to avoid leaking environment or token values from the process
        stderr = result.stderr.strip()[:300].replace("\n", " ") if result.stderr else "(no stderr)"
        raise LLMError(f"Claude CLI exited with code {result.returncode}: {stderr}")

    output = result.stdout.strip()
    if not output:
        stderr = result.stderr.strip()[:300].replace("\n", " ") if result.stderr else "(no stderr)"
        raise LLMError(f"Claude CLI returned empty output. stderr: {stderr}")

    return output


def _call_anthropic(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    system: str,
) -> str:
    """Call Anthropic Messages API with API key auth."""
    url = f"{base_url}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise LLMError(f"HTTP error calling Anthropic API: {e}") from e

    if resp.status_code != 200:
        # Truncate and strip — never echo request headers (which contain the API key)
        safe_body = resp.text[:300].replace("\n", " ")
        raise LLMError(f"Anthropic API returned {resp.status_code}: {safe_body}")

    try:
        data = resp.json()
        # Anthropic response: {"content": [{"type": "text", "text": "..."}]}
        content_blocks = data.get("content", [])
        text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
        return "".join(text_parts)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise LLMError(f"Failed to parse Anthropic response: {type(e).__name__}") from e


def _call_openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    system: str,
) -> str:
    """Call OpenAI-compatible Chat Completions API."""
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": model,
        "messages": messages,
        "max_tokens": 8192,
    }

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise LLMError(f"HTTP error calling OpenAI-compatible API: {e}") from e

    if resp.status_code != 200:
        safe_body = resp.text[:300].replace("\n", " ")
        raise LLMError(f"OpenAI-compatible API returned {resp.status_code}: {safe_body}")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Failed to parse OpenAI-compatible response: {type(e).__name__}") from e
