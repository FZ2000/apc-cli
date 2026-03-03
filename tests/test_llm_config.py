"""Unit tests for LLM configuration module."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestAuthProfiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.auth_path = Path(self.tmpdir) / "auth-profiles.json"
        self.models_path = Path(self.tmpdir) / "models.json"

    def _patch_paths(self):
        return (
            patch("apc.llm_config._auth_profiles_path", return_value=self.auth_path),
            patch("apc.llm_config._models_path", return_value=self.models_path),
        )

    def test_add_and_load_profile(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import add_auth_profile, load_auth_profiles

            key = add_auth_profile("anthropic", "default", "api_key", key="sk-ant-test123")

            self.assertEqual(key, "anthropic:default")
            data = load_auth_profiles()
            self.assertIn("anthropic:default", data["profiles"])
            self.assertEqual(data["profiles"]["anthropic:default"]["key"], "sk-ant-test123")
            self.assertEqual(data["profiles"]["anthropic:default"]["type"], "api_key")
            self.assertEqual(data["profiles"]["anthropic:default"]["provider"], "anthropic")

    def test_remove_profile(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import add_auth_profile, load_auth_profiles, remove_auth_profile

            add_auth_profile("openai", "default", "api_key", key="sk-test")
            result = remove_auth_profile("openai:default")

            self.assertTrue(result)
            data = load_auth_profiles()
            self.assertNotIn("openai:default", data["profiles"])

    def test_remove_nonexistent_profile(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import remove_auth_profile

            result = remove_auth_profile("nonexistent:profile")
            self.assertFalse(result)

    def test_get_auth_profile(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import add_auth_profile, get_auth_profile

            add_auth_profile("anthropic", "work", "api_key", key="sk-work")

            profile = get_auth_profile("anthropic:work")
            self.assertIsNotNone(profile)
            self.assertEqual(profile["key"], "sk-work")

    def test_get_default_profile_for_provider(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import add_auth_profile, get_default_profile_for_provider

            add_auth_profile("anthropic", "default", "api_key", key="sk-default")
            add_auth_profile("anthropic", "work", "api_key", key="sk-work")

            profile = get_default_profile_for_provider("anthropic")
            self.assertIsNotNone(profile)
            self.assertEqual(profile["key"], "sk-default")

    def test_multiple_profiles_order(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import add_auth_profile, load_auth_profiles

            add_auth_profile("anthropic", "default", "api_key", key="sk-1")
            add_auth_profile("anthropic", "work", "api_key", key="sk-2")

            data = load_auth_profiles()
            order = data["order"]["anthropic"]
            self.assertEqual(order, ["anthropic:default", "anthropic:work"])


class TestModelsConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.auth_path = Path(self.tmpdir) / "auth-profiles.json"
        self.models_path = Path(self.tmpdir) / "models.json"

    def _patch_paths(self):
        return (
            patch("apc.llm_config._auth_profiles_path", return_value=self.auth_path),
            patch("apc.llm_config._models_path", return_value=self.models_path),
        )

    def test_set_and_get_default_model(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import get_default_model, set_default_model

            set_default_model("anthropic/claude-sonnet-4-6")
            result = get_default_model()

            self.assertEqual(result, "anthropic/claude-sonnet-4-6")

    def test_get_default_model_none(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import get_default_model

            result = get_default_model()
            self.assertIsNone(result)

    def test_ensure_provider_in_models(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import ensure_provider_in_models, load_models_config

            ensure_provider_in_models(
                "anthropic",
                "https://api.anthropic.com",
                "anthropic-messages",
                ["claude-sonnet-4-6", "claude-haiku-4-5"],
            )

            data = load_models_config()
            self.assertIn("anthropic", data["providers"])
            self.assertEqual(data["providers"]["anthropic"]["api"], "anthropic-messages")

    def test_ensure_provider_idempotent(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import ensure_provider_in_models, load_models_config

            ensure_provider_in_models(
                "openai", "https://api.openai.com/v1", "openai-completions", ["gpt-4o"]
            )
            ensure_provider_in_models(
                "openai", "https://different.url", "openai-completions", ["gpt-4o-mini"]
            )

            data = load_models_config()
            # Should keep original (not overwrite)
            self.assertEqual(data["providers"]["openai"]["baseUrl"], "https://api.openai.com/v1")

    def test_resolve_model(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import ensure_provider_in_models, resolve_model, set_default_model

            ensure_provider_in_models(
                "anthropic",
                "https://api.anthropic.com",
                "anthropic-messages",
                ["claude-sonnet-4-6"],
            )
            set_default_model("anthropic/claude-sonnet-4-6")

            result = resolve_model()
            self.assertIsNotNone(result)
            self.assertEqual(result["provider"], "anthropic")
            self.assertEqual(result["model"], "claude-sonnet-4-6")
            self.assertEqual(result["api_dialect"], "anthropic-messages")

    def test_resolve_model_none_when_not_configured(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import resolve_model

            result = resolve_model()
            self.assertIsNone(result)


class TestResolveApiKey(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.auth_path = Path(self.tmpdir) / "auth-profiles.json"
        self.models_path = Path(self.tmpdir) / "models.json"

    def _patch_paths(self):
        return (
            patch("apc.llm_config._auth_profiles_path", return_value=self.auth_path),
            patch("apc.llm_config._models_path", return_value=self.models_path),
        )

    def test_resolve_from_profile(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import add_auth_profile, resolve_api_key

            add_auth_profile("anthropic", "default", "api_key", key="sk-saved")

            result = resolve_api_key("anthropic")
            self.assertEqual(result, "sk-saved")

    def test_resolve_from_explicit_profile(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import add_auth_profile, resolve_api_key

            add_auth_profile("anthropic", "default", "api_key", key="sk-default")
            add_auth_profile("anthropic", "work", "api_key", key="sk-work")

            result = resolve_api_key("anthropic", "anthropic:work")
            self.assertEqual(result, "sk-work")

    def test_resolve_from_env_var(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import resolve_api_key

            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-key"}):
                result = resolve_api_key("anthropic")
                self.assertEqual(result, "sk-env-key")

    def test_resolve_none_when_not_configured(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import resolve_api_key

            with patch.dict(os.environ, {}, clear=True):
                result = resolve_api_key("anthropic")
                self.assertIsNone(result)


class TestProviderRegistry(unittest.TestCase):
    def test_all_required_providers_present(self):
        from apc.llm_config import PROVIDERS

        expected = {"anthropic", "openai", "gemini", "qwen", "glm", "minimax", "kimi", "custom"}
        self.assertEqual(set(PROVIDERS.keys()), expected)

    def test_all_providers_have_required_fields(self):
        from apc.llm_config import PROVIDERS

        for name, pdef in PROVIDERS.items():
            self.assertTrue(pdef.name, f"{name} missing name")
            self.assertTrue(pdef.auth_methods, f"{name} missing auth_methods")
            self.assertIn(
                pdef.api_dialect,
                ["anthropic-messages", "openai-completions"],
                f"{name} has invalid api_dialect",
            )

    def test_anthropic_uses_anthropic_dialect(self):
        from apc.llm_config import PROVIDERS

        self.assertEqual(PROVIDERS["anthropic"].api_dialect, "anthropic-messages")

    def test_openai_uses_openai_dialect(self):
        from apc.llm_config import PROVIDERS

        self.assertEqual(PROVIDERS["openai"].api_dialect, "openai-completions")


class TestNonInteractiveConfigure(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.auth_path = Path(self.tmpdir) / "auth-profiles.json"
        self.models_path = Path(self.tmpdir) / "models.json"

    def _patch_paths(self):
        return (
            patch("apc.llm_config._auth_profiles_path", return_value=self.auth_path),
            patch("apc.llm_config._models_path", return_value=self.models_path),
        )

    def test_configure_anthropic(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import (
                configure_non_interactive,
                get_default_model,
                load_auth_profiles,
            )

            key = configure_non_interactive(
                provider="anthropic",
                auth_method="api_key",
                api_key="sk-ant-test",
            )

            self.assertEqual(key, "anthropic:default")
            profiles = load_auth_profiles()
            self.assertIn("anthropic:default", profiles["profiles"])
            self.assertEqual(get_default_model(), "anthropic/claude-sonnet-4-6")

    def test_configure_custom_provider(self):
        p1, p2 = self._patch_paths()
        with p1, p2:
            from apc.llm_config import configure_non_interactive, load_models_config

            configure_non_interactive(
                provider="custom",
                auth_method="api_key",
                api_key="sk-custom",
                base_url="http://localhost:4000/v1",
                model_id="llama-3",
            )

            models = load_models_config()
            self.assertIn("custom", models["providers"])
            self.assertEqual(models["default"], "custom/llama-3")


if __name__ == "__main__":
    unittest.main()
