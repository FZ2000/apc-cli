"""Security tests for LLM base_url validation (CVE-2026-21852 analog).

Ensures that a malicious or malformed base_url in ~/.apc/models.json cannot
redirect API calls (and thus API keys) to an attacker-controlled endpoint.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_client import LLMError, _validate_base_url

# ---------------------------------------------------------------------------
# Valid URLs — must not raise
# ---------------------------------------------------------------------------


class TestValidUrls:
    def test_anthropic_https(self):
        _validate_base_url("https://api.anthropic.com")

    def test_openai_https(self):
        _validate_base_url("https://api.openai.com/v1")

    def test_gemini_https(self):
        _validate_base_url("https://generativelanguage.googleapis.com/v1beta/openai")

    def test_custom_http_localhost(self):
        """Local/custom endpoints are allowed over HTTP (e.g. Ollama)."""
        _validate_base_url("http://127.0.0.1:11434/v1")

    def test_custom_http_localhost_named(self):
        _validate_base_url("http://localhost:4000/v1")

    def test_custom_http_internal_network(self):
        """Private network ranges are valid for self-hosted deployments."""
        _validate_base_url("http://192.168.1.100:8080/api")

    def test_custom_https_proxy(self):
        _validate_base_url("https://my-proxy.internal.example.com/llm")

    def test_moonshot_https(self):
        _validate_base_url("https://api.moonshot.cn/v1")


# ---------------------------------------------------------------------------
# Invalid URLs — must raise LLMError
# ---------------------------------------------------------------------------


class TestInvalidUrls:
    def test_empty_string(self):
        with pytest.raises(LLMError, match="empty or invalid"):
            _validate_base_url("")

    def test_none_value(self):
        with pytest.raises(LLMError):
            _validate_base_url(None)  # type: ignore[arg-type]

    def test_non_string(self):
        with pytest.raises(LLMError):
            _validate_base_url(42)  # type: ignore[arg-type]

    def test_file_scheme(self):
        """file:// URLs must be rejected to prevent reading local secrets."""
        with pytest.raises(LLMError, match="unsupported scheme"):
            _validate_base_url("file:///etc/passwd")

    def test_ftp_scheme(self):
        with pytest.raises(LLMError, match="unsupported scheme"):
            _validate_base_url("ftp://evil.example.com")

    def test_javascript_scheme(self):
        with pytest.raises(LLMError, match="unsupported scheme"):
            _validate_base_url("javascript:alert(1)")

    def test_data_scheme(self):
        with pytest.raises(LLMError, match="unsupported scheme"):
            _validate_base_url("data:text/html,<h1>hi</h1>")

    def test_no_scheme(self):
        """Bare hostnames without scheme must be rejected."""
        with pytest.raises(LLMError):
            _validate_base_url("evil.example.com/v1")

    def test_leading_whitespace(self):
        with pytest.raises(LLMError, match="whitespace"):
            _validate_base_url("  https://api.anthropic.com")

    def test_trailing_whitespace(self):
        with pytest.raises(LLMError, match="whitespace"):
            _validate_base_url("https://api.anthropic.com  ")

    def test_embedded_credentials_user_pass(self):
        """user:pass@host URLs must be rejected to prevent credential leakage."""
        with pytest.raises(LLMError, match="credentials"):
            _validate_base_url("https://user:password@api.anthropic.com")

    def test_embedded_credentials_user_only(self):
        with pytest.raises(LLMError, match="credentials"):
            _validate_base_url("https://user@api.anthropic.com")


# ---------------------------------------------------------------------------
# Cloud providers must use HTTPS
# ---------------------------------------------------------------------------


class TestCloudHttpsEnforcement:
    """Known cloud endpoints must use HTTPS to prevent plaintext key transmission."""

    def test_anthropic_http_rejected(self):
        with pytest.raises(LLMError, match="HTTPS"):
            _validate_base_url("http://api.anthropic.com")

    def test_openai_http_rejected(self):
        with pytest.raises(LLMError, match="HTTPS"):
            _validate_base_url("http://api.openai.com/v1")

    def test_gemini_http_rejected(self):
        with pytest.raises(LLMError, match="HTTPS"):
            _validate_base_url("http://generativelanguage.googleapis.com/v1beta/openai")

    def test_moonshot_http_rejected(self):
        with pytest.raises(LLMError, match="HTTPS"):
            _validate_base_url("http://api.moonshot.cn/v1")

    def test_custom_unknown_host_http_allowed(self):
        """Non-cloud hostnames are not forced to HTTPS (local/custom deployments)."""
        _validate_base_url("http://my-custom-host.example.com/v1")


# ---------------------------------------------------------------------------
# Integration: _validate_base_url called before HTTP in call_llm
# ---------------------------------------------------------------------------


class TestCallLlmValidatesUrl:
    def test_call_llm_rejects_invalid_base_url_before_http(self):
        """call_llm must validate base_url before making any HTTP request."""
        from unittest.mock import patch

        with (
            patch(
                "llm_client.resolve_model",
                return_value={
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-6",
                    "api_dialect": "anthropic-messages",
                    "base_url": "http://api.anthropic.com",  # HTTP on cloud host — invalid
                },
            ),
            patch("llm_client.resolve_auth_type", return_value="api_key"),
            patch("llm_client.resolve_api_key", return_value="sk-test-key"),
            patch("httpx.Client") as mock_client,
        ):
            from llm_client import call_llm

            with pytest.raises(LLMError, match="HTTPS"):
                call_llm("hello")

        # httpx must NOT have been called (validation blocks it)
        mock_client.assert_not_called()

    def test_call_llm_rejects_file_url_before_http(self):
        """file:// base_url must be blocked before any HTTP call."""
        from unittest.mock import patch

        with (
            patch(
                "llm_client.resolve_model",
                return_value={
                    "provider": "custom",
                    "model": "llama",
                    "api_dialect": "openai-completions",
                    "base_url": "file:///etc/passwd",
                },
            ),
            patch("llm_client.resolve_auth_type", return_value="api_key"),
            patch("llm_client.resolve_api_key", return_value="x"),
            patch("httpx.Client") as mock_client,
        ):
            from llm_client import call_llm

            with pytest.raises(LLMError, match="unsupported scheme"):
                call_llm("hello")

        mock_client.assert_not_called()
