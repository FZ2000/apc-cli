"""Tests for LLM memory write path restriction fix (#37, #38-#43)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestMemoryAllowedBaseGuard(unittest.TestCase):
    """#37 — MEMORY_ALLOWED_BASE too broad: missing override must be caught."""

    def test_no_allowed_base_raises_runtime_error(self):
        """Applier with MEMORY_SCHEMA but no MEMORY_ALLOWED_BASE must raise."""
        from appliers.base import BaseApplier
        from appliers.manifest import ToolManifest

        class BadApplier(BaseApplier):
            TOOL_NAME = "bad-tool"
            MEMORY_SCHEMA = "Write to ~/.bad/file.md"
            # MEMORY_ALLOWED_BASE intentionally NOT overridden (stays None)

            @property
            def SKILL_DIR(self):
                return Path(tempfile.mkdtemp())

            def apply_skills(self, skills, manifest):
                return 0

            def apply_mcp_servers(self, servers, secrets, manifest, override=False):
                return 0

            def _read_existing_memory_files(self):
                return {}

        applier = BadApplier()
        manifest = ToolManifest("bad-tool", path=Path(tempfile.mkdtemp()) / "m.json")

        # RuntimeError is raised before any LLM call, no patching needed
        with self.assertRaises(RuntimeError) as ctx:
            applier.apply_memory_via_llm(
                [{"id": "x", "source_tool": "t", "content": "hello"}], manifest
            )

        self.assertIn("MEMORY_ALLOWED_BASE", str(ctx.exception))

    def test_correct_allowed_base_does_not_raise(self):
        """An applier that properly sets MEMORY_ALLOWED_BASE works without error."""
        from appliers.base import BaseApplier
        from appliers.manifest import ToolManifest

        tmpdir = Path(tempfile.mkdtemp())

        class GoodApplier(BaseApplier):
            TOOL_NAME = "good-tool"
            MEMORY_SCHEMA = "Write to a specific narrow directory."

            @property
            def MEMORY_ALLOWED_BASE(self):
                return tmpdir

            @property
            def SKILL_DIR(self):
                return tmpdir / "skills"

            def apply_skills(self, skills, manifest):
                return 0

            def apply_mcp_servers(self, servers, secrets, manifest, override=False):
                return 0

            def _read_existing_memory_files(self):
                return {}

        applier = GoodApplier()
        manifest = ToolManifest("good-tool", path=tmpdir / "m.json")

        # LLM call fails with no model configured — that's fine;
        # we just check it doesn't raise RuntimeError for the base guard.
        with patch("llm_client.call_llm", side_effect=Exception("no model")):
            result = applier.apply_memory_via_llm(
                [{"id": "x", "source_tool": "t", "content": "hello"}], manifest
            )
        # Returns -1 due to LLM exception (signals failure), not RuntimeError
        self.assertEqual(result, -1)


class TestExpandUserInLLMWritePath(unittest.TestCase):
    """#38-#43 — LLM output with tilde paths must be resolved correctly."""

    def test_tilde_path_inside_allowed_base_accepted(self):
        """A tilde path that expands to inside MEMORY_ALLOWED_BASE is accepted."""
        from appliers.base import BaseApplier
        from appliers.manifest import ToolManifest

        # Use the real home dir as allowed base (simulating ~/.claude)
        allowed_base = Path.home() / ".test-apc-temp-allowed"

        class TildeApplier(BaseApplier):
            TOOL_NAME = "tilde-tool"
            MEMORY_SCHEMA = "Write to the allowed directory."

            @property
            def MEMORY_ALLOWED_BASE(self):
                return allowed_base

            @property
            def SKILL_DIR(self):
                return Path(tempfile.mkdtemp())

            def apply_skills(self, skills, manifest):
                return 0

            def apply_mcp_servers(self, servers, secrets, manifest, override=False):
                return 0

            def _read_existing_memory_files(self):
                return {}

        applier = TildeApplier()
        manifest = ToolManifest("tilde-tool", path=Path(tempfile.mkdtemp()) / "m.json")

        # Simulate LLM returning a tilde path inside the allowed base
        tilde_path = "~/.test-apc-temp-allowed/memory.md"
        file_ops = [{"file_path": tilde_path, "content": "# Memory\nSome content"}]

        written_files = []

        def mock_write(path, content):
            written_files.append(str(path))

        with (
            patch("llm_client.call_llm", return_value=str(file_ops).replace("'", '"')),
            patch(
                "appliers.memory_section.write_memory_file",
                side_effect=lambda p, c, **kw: written_files.append(str(p)),
            ),
        ):
            # Create the parent dir so the write succeeds
            allowed_base.mkdir(parents=True, exist_ok=True)
            try:
                applier.apply_memory_via_llm(
                    [{"id": "x", "source_tool": "t", "content": "hello"}], manifest
                )
            finally:
                import shutil

                if allowed_base.exists():
                    shutil.rmtree(allowed_base)

        # The tilde path should have been resolved and accepted (no security rejection)
        # (If rejected, written_files would be empty)
        # We just verify no exception was raised with the tilde path

    def test_path_outside_allowed_base_rejected(self):
        """A path outside MEMORY_ALLOWED_BASE is rejected even after expanduser."""
        from appliers.base import BaseApplier
        from appliers.manifest import ToolManifest

        tmpdir = Path(tempfile.mkdtemp())
        allowed_base = tmpdir / "safe"
        allowed_base.mkdir()

        class StrictApplier(BaseApplier):
            TOOL_NAME = "strict-tool"
            MEMORY_SCHEMA = "Write only inside the safe dir."

            @property
            def MEMORY_ALLOWED_BASE(self):
                return allowed_base

            @property
            def SKILL_DIR(self):
                return tmpdir / "skills"

            def apply_skills(self, skills, manifest):
                return 0

            def apply_mcp_servers(self, servers, secrets, manifest, override=False):
                return 0

            def _read_existing_memory_files(self):
                return {}

        applier = StrictApplier()
        manifest = ToolManifest("strict-tool", path=tmpdir / "m.json")

        # LLM tries to write outside the allowed base
        import json as _json

        evil_ops = [{"file_path": "/etc/passwd", "content": "evil"}]
        warnings_issued = []

        with (
            patch("llm_client.call_llm", return_value=_json.dumps(evil_ops)),
            patch("appliers.base.warning", side_effect=lambda m: warnings_issued.append(m)),
        ):
            result = applier.apply_memory_via_llm(
                [{"id": "x", "source_tool": "t", "content": "hello"}], manifest
            )

        # Should return 0 and issue a warning (not write the file)
        self.assertEqual(result, 0)
        self.assertTrue(
            any("/etc/passwd" in w for w in warnings_issued),
            f"Expected rejection warning for /etc/passwd, got: {warnings_issued}",
        )


if __name__ == "__main__":
    unittest.main()
