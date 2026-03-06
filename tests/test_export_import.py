"""Tests for export/import functionality and age encryption."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from export_import import (
    AGE_PREFIX,
    SCHEMA_VERSION,
    _export_auth_profiles,
    _export_mcp_servers,
    _import_auth_profiles,
    _import_mcp_servers,
    decrypt_value,
    encrypt_value,
    export_cmd,
    import_cmd,
    is_encrypted,
)


class TestAgeEncryption(unittest.TestCase):
    """Test encrypt/decrypt round-trip with pyrage."""

    def setUp(self):
        try:
            from pyrage import x25519

            identity = x25519.Identity.generate()
            self.public_key = str(identity.to_public())
            self.private_key = str(identity)
            self.pyrage_available = True
        except ImportError:
            self.pyrage_available = False

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("pyrage"),
        "pyrage not installed",
    )
    def test_encrypt_decrypt_round_trip(self):
        plaintext = "sk-ant-api03-secret-key-here"
        encrypted = encrypt_value(plaintext, self.public_key)

        self.assertTrue(encrypted.startswith(AGE_PREFIX))
        self.assertNotEqual(encrypted, plaintext)

        decrypted = decrypt_value(encrypted, self.private_key)
        self.assertEqual(decrypted, plaintext)

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("pyrage"),
        "pyrage not installed",
    )
    def test_encrypt_empty_string(self):
        encrypted = encrypt_value("", self.public_key)
        self.assertTrue(encrypted.startswith(AGE_PREFIX))
        decrypted = decrypt_value(encrypted, self.private_key)
        self.assertEqual(decrypted, "")

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("pyrage"),
        "pyrage not installed",
    )
    def test_decrypt_wrong_key_returns_none(self):
        from pyrage import x25519

        other = x25519.Identity.generate()
        encrypted = encrypt_value("secret", self.public_key)
        result = decrypt_value(encrypted, str(other))
        self.assertIsNone(result)

    def test_decrypt_non_encrypted_passes_through(self):
        result = decrypt_value("plain-text-value", "unused-key")
        self.assertEqual(result, "plain-text-value")

    def test_is_encrypted(self):
        self.assertTrue(is_encrypted("AGE:abc123"))
        self.assertFalse(is_encrypted("plain"))
        self.assertFalse(is_encrypted(""))


class TestExportMCPServers(unittest.TestCase):
    """Test MCP server export with secret encryption."""

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("pyrage"),
        "pyrage not installed",
    )
    def test_encrypts_secrets_from_keychain(self):
        from pyrage import x25519

        identity = x25519.Identity.generate()
        pub = str(identity.to_public())
        priv = str(identity)

        servers = [
            {
                "name": "test-server",
                "transport": "stdio",
                "command": "node",
                "args": ["server.js"],
                "env": {"TOKEN": "${TOKEN}", "URL": "http://localhost"},
                "secret_placeholders": ["TOKEN"],
                "source_tool": "claude",
            }
        ]

        with patch("export_import.retrieve_secret", return_value="my-secret-token"):
            result = _export_mcp_servers(servers, pub)

        self.assertEqual(len(result), 1)
        self.assertIn("encrypted_secrets", result[0])
        self.assertTrue(result[0]["encrypted_secrets"]["TOKEN"].startswith(AGE_PREFIX))

        # Verify round-trip
        decrypted = decrypt_value(result[0]["encrypted_secrets"]["TOKEN"], priv)
        self.assertEqual(decrypted, "my-secret-token")

    def test_no_encryption_without_key(self):
        servers = [
            {
                "name": "test",
                "secret_placeholders": ["TOKEN"],
            }
        ]
        with patch("export_import.retrieve_secret", return_value="secret"):
            result = _export_mcp_servers(servers, None)

        self.assertNotIn("encrypted_secrets", result[0])

    def test_missing_secret_warns_and_skips(self):
        servers = [
            {
                "name": "test",
                "secret_placeholders": ["MISSING_TOKEN"],
            }
        ]
        # pyrage needed for public key
        try:
            from pyrage import x25519

            pub = str(x25519.Identity.generate().to_public())
        except ImportError:
            self.skipTest("pyrage not installed")

        with patch("export_import.retrieve_secret", return_value=None):
            result = _export_mcp_servers(servers, pub)

        # Should not have encrypted_secrets since the secret was missing
        self.assertNotIn("encrypted_secrets", result[0])


class TestImportMCPServers(unittest.TestCase):
    """Test MCP server import with secret decryption."""

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("pyrage"),
        "pyrage not installed",
    )
    def test_decrypts_secrets(self):
        from pyrage import x25519

        identity = x25519.Identity.generate()
        pub = str(identity.to_public())
        priv = str(identity)

        encrypted = encrypt_value("my-token", pub)
        servers = [
            {
                "name": "test-server",
                "env": {"TOKEN": "${TOKEN}"},
                "secret_placeholders": ["TOKEN"],
                "encrypted_secrets": {"TOKEN": encrypted},
            }
        ]

        clean, secrets = _import_mcp_servers(servers, priv)

        self.assertEqual(secrets, {"TOKEN": "my-token"})
        self.assertNotIn("encrypted_secrets", clean[0])

    def test_no_key_skips_decryption(self):
        servers = [
            {
                "name": "test-server",
                "encrypted_secrets": {"TOKEN": "AGE:abc123"},
            }
        ]
        clean, secrets = _import_mcp_servers(servers, None)

        self.assertEqual(secrets, {})
        self.assertNotIn("encrypted_secrets", clean[0])

    def test_no_encrypted_secrets_is_passthrough(self):
        servers = [{"name": "plain-server", "env": {"URL": "http://localhost"}}]
        clean, secrets = _import_mcp_servers(servers, None)

        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0]["name"], "plain-server")
        self.assertEqual(secrets, {})


class TestExportAuthProfiles(unittest.TestCase):
    """Test auth profile export with encryption."""

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("pyrage"),
        "pyrage not installed",
    )
    def test_encrypts_key_and_token(self):
        from pyrage import x25519

        identity = x25519.Identity.generate()
        pub = str(identity.to_public())
        priv = str(identity)

        data = {
            "version": 1,
            "profiles": {
                "anthropic:default": {
                    "type": "api_key",
                    "provider": "anthropic",
                    "key": "sk-ant-api03-secret",
                },
                "anthropic:token": {
                    "type": "token",
                    "provider": "anthropic",
                    "token": "setup-token-value",
                },
            },
            "order": {"anthropic": ["anthropic:default", "anthropic:token"]},
        }

        result = _export_auth_profiles(data, pub)

        # Keys should be encrypted
        self.assertTrue(result["profiles"]["anthropic:default"]["key"].startswith(AGE_PREFIX))
        self.assertTrue(result["profiles"]["anthropic:token"]["token"].startswith(AGE_PREFIX))

        # Round-trip
        self.assertEqual(
            decrypt_value(result["profiles"]["anthropic:default"]["key"], priv),
            "sk-ant-api03-secret",
        )

    def test_no_encryption_without_key(self):
        data = {
            "version": 1,
            "profiles": {
                "openai:default": {"type": "api_key", "key": "sk-openai"},
            },
            "order": {},
        }
        result = _export_auth_profiles(data, None)
        self.assertEqual(result["profiles"]["openai:default"]["key"], "sk-openai")


class TestImportAuthProfiles(unittest.TestCase):
    """Test auth profile import with decryption."""

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("pyrage"),
        "pyrage not installed",
    )
    def test_decrypts_profiles(self):
        from pyrage import x25519

        identity = x25519.Identity.generate()
        pub = str(identity.to_public())
        priv = str(identity)

        encrypted_key = encrypt_value("sk-real-key", pub)
        data = {
            "version": 1,
            "profiles": {
                "openai:default": {
                    "type": "api_key",
                    "provider": "openai",
                    "key": encrypted_key,
                },
            },
            "order": {},
        }

        result = _import_auth_profiles(data, priv)
        self.assertEqual(result["profiles"]["openai:default"]["key"], "sk-real-key")

    def test_no_key_clears_encrypted_fields(self):
        data = {
            "version": 1,
            "profiles": {
                "test:default": {
                    "type": "api_key",
                    "key": "AGE:encrypted-data",
                },
            },
            "order": {},
        }
        result = _import_auth_profiles(data, None)
        self.assertEqual(result["profiles"]["test:default"]["key"], "")


class TestExportCommand(unittest.TestCase):
    """Test the export CLI command end-to-end."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.export_dir = Path(self.tmpdir) / "test-export"

    @patch("export_import._check_pyrage", return_value=False)
    @patch("export_import.get_skills_dir")
    @patch("export_import.get_config_dir")
    @patch("export_import.load_mcp_servers", return_value=[])
    @patch(
        "export_import.load_local_bundle",
        return_value={"skills": [], "mcp_servers": [], "memory": []},
    )
    def test_export_creates_structure(
        self, mock_bundle, mock_mcp, mock_config, mock_skills, mock_pyrage
    ):
        config_dir = Path(self.tmpdir) / "config"
        config_dir.mkdir()
        mock_config.return_value = config_dir
        mock_skills.return_value = config_dir / "skills"

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(export_cmd, [str(self.export_dir), "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.export_dir / "apc-export.json").exists())
        self.assertTrue((self.export_dir / "cache" / "skills.json").exists())
        self.assertTrue((self.export_dir / "cache" / "mcp_servers.json").exists())
        self.assertTrue((self.export_dir / "cache" / "memory.json").exists())

        meta = json.loads((self.export_dir / "apc-export.json").read_text())
        self.assertEqual(meta["schema_version"], SCHEMA_VERSION)
        self.assertIsNone(meta["public_key"])

    @patch("export_import._check_pyrage", return_value=False)
    @patch("export_import.get_skills_dir")
    @patch("export_import.get_config_dir")
    @patch("export_import.load_mcp_servers", return_value=[])
    @patch(
        "export_import.load_local_bundle",
        return_value={
            "skills": [{"name": "test-skill", "body": "# Test"}],
            "mcp_servers": [],
            "memory": [{"id": "mem1", "content": "Remember this"}],
        },
    )
    def test_export_writes_cache_data(
        self, mock_bundle, mock_mcp, mock_config, mock_skills, mock_pyrage
    ):
        config_dir = Path(self.tmpdir) / "config"
        config_dir.mkdir()
        mock_config.return_value = config_dir
        mock_skills.return_value = config_dir / "skills"

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(export_cmd, [str(self.export_dir), "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)

        skills = json.loads((self.export_dir / "cache" / "skills.json").read_text())
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["name"], "test-skill")

        memory = json.loads((self.export_dir / "cache" / "memory.json").read_text())
        self.assertEqual(len(memory), 1)


class TestImportCommand(unittest.TestCase):
    """Test the import CLI command end-to-end."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.export_dir = Path(self.tmpdir) / "test-export"
        self._create_export_fixture()

    def _create_export_fixture(self):
        """Create a minimal valid export directory."""
        self.export_dir.mkdir(parents=True)
        (self.export_dir / "cache").mkdir()
        (self.export_dir / "config").mkdir()

        meta = {
            "schema_version": SCHEMA_VERSION,
            "created_at": "2026-01-01T00:00:00+00:00",
            "public_key": None,
            "stats": {"skills": 1, "mcp_servers": 0, "memory": 1, "installed_skills": 0},
        }
        (self.export_dir / "apc-export.json").write_text(json.dumps(meta))
        (self.export_dir / "cache" / "skills.json").write_text(
            json.dumps([{"name": "imported-skill", "body": "# Imported"}])
        )
        (self.export_dir / "cache" / "mcp_servers.json").write_text(json.dumps([]))
        (self.export_dir / "cache" / "memory.json").write_text(
            json.dumps([{"id": "m1", "content": "Imported memory"}])
        )

    @patch("export_import._check_pyrage", return_value=False)
    @patch("export_import.get_skills_dir")
    @patch("export_import.get_config_dir")
    @patch("export_import.save_mcp_servers")
    @patch("export_import.load_mcp_servers", return_value=[])
    @patch("export_import.save_memory")
    @patch("export_import.save_skills")
    @patch(
        "export_import.load_local_bundle",
        return_value={"skills": [], "mcp_servers": [], "memory": []},
    )
    def test_import_merges_cache(
        self,
        mock_bundle,
        mock_save_skills,
        mock_save_memory,
        mock_load_mcp,
        mock_save_mcp,
        mock_config,
        mock_skills,
        mock_pyrage,
    ):
        config_dir = Path(self.tmpdir) / "config"
        config_dir.mkdir(exist_ok=True)
        mock_config.return_value = config_dir
        mock_skills.return_value = config_dir / "skills"

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(import_cmd, [str(self.export_dir), "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)
        mock_save_skills.assert_called_once()
        mock_save_memory.assert_called_once()

        # Verify merged data
        saved_skills = mock_save_skills.call_args[0][0]
        self.assertEqual(len(saved_skills), 1)
        self.assertEqual(saved_skills[0]["name"], "imported-skill")

    def test_import_rejects_invalid_directory(self):
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(import_cmd, ["/nonexistent/path", "--yes"])
        self.assertNotEqual(result.exit_code, 0)

    def test_import_rejects_future_schema(self):
        meta = {
            "schema_version": 999,
            "created_at": "2026-01-01T00:00:00+00:00",
            "public_key": None,
            "stats": {},
        }
        (self.export_dir / "apc-export.json").write_text(json.dumps(meta))

        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(import_cmd, [str(self.export_dir), "--yes"])
        self.assertNotEqual(result.exit_code, 0)


class TestSyncHelpersMCPSecretsFix(unittest.TestCase):
    """Test that _resolve_all_mcp_secrets works correctly."""

    def test_resolves_secrets_from_keychain(self):
        from sync_helpers import _resolve_all_mcp_secrets

        servers = [
            {
                "name": "server-a",
                "env": {"TOKEN": "${TOKEN}", "URL": "http://localhost"},
                "secret_placeholders": ["TOKEN"],
            },
            {
                "name": "server-b",
                "env": {"API_KEY": "${API_KEY}"},
                "secret_placeholders": ["API_KEY"],
            },
        ]

        with patch("sync_helpers.retrieve_secret") as mock_retrieve:
            mock_retrieve.side_effect = lambda uid, key: {
                "TOKEN": "token-value",
                "API_KEY": "key-value",
            }.get(key)

            result = _resolve_all_mcp_secrets(servers)

        self.assertEqual(result, {"TOKEN": "token-value", "API_KEY": "key-value"})

    def test_missing_secret_excluded(self):
        from sync_helpers import _resolve_all_mcp_secrets

        servers = [
            {
                "name": "server",
                "secret_placeholders": ["MISSING"],
            }
        ]

        with patch("sync_helpers.retrieve_secret", return_value=None):
            result = _resolve_all_mcp_secrets(servers)

        self.assertEqual(result, {})

    def test_no_placeholders(self):
        from sync_helpers import _resolve_all_mcp_secrets

        servers = [{"name": "plain", "env": {"URL": "http://localhost"}}]
        result = _resolve_all_mcp_secrets(servers)
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
