"""Tests for CopilotExtractor call-time path resolution (#42).

The bug: COPILOT_INSTRUCTIONS and VSCODE_MCP_JSON were module-level
Path("...") constants, resolved relative to the CWD at *import* time.
If the module was imported from a different directory than the user's home,
the paths would be wrong for the entire process lifetime.

The fix: _copilot_instructions() and _vscode_mcp_json() are call-time
accessor functions that re-evaluate Path.cwd().resolve() on every call.

These tests verify:
  1. Accessor functions return absolute paths
  2. Paths are resolved from the current working directory at call time,
     not at module import time (the core regression check)
  3. extract_skills() reads from the correct absolute path
  4. extract_mcp_servers() reads from the correct absolute path
  5. source_path in extracted skills is absolute
  6. extract_skills() returns empty list when file absent
  7. extract_mcp_servers() returns empty list when file absent
  8. extract_mcp_servers() handles malformed JSON gracefully
  9. extract_memory() always returns empty list
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extractors.copilot import CopilotExtractor, _copilot_instructions, _vscode_mcp_json

# ---------------------------------------------------------------------------
# Accessor function unit tests
# ---------------------------------------------------------------------------


class TestAccessorFunctions:
    def test_copilot_instructions_is_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _copilot_instructions()
        assert result.is_absolute(), f"Expected absolute path, got: {result}"

    def test_vscode_mcp_json_is_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _vscode_mcp_json()
        assert result.is_absolute(), f"Expected absolute path, got: {result}"

    def test_copilot_instructions_resolves_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _copilot_instructions()
        assert result == tmp_path.resolve() / ".github" / "copilot-instructions.md"

    def test_vscode_mcp_json_resolves_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _vscode_mcp_json()
        assert result == tmp_path.resolve() / ".vscode" / "mcp.json"

    def test_copilot_instructions_changes_with_cwd(self, tmp_path, monkeypatch):
        """Core regression test: path must re-resolve on every call, not be frozen."""
        dir_a = tmp_path / "dir_a"
        dir_b = tmp_path / "dir_b"
        dir_a.mkdir()
        dir_b.mkdir()

        monkeypatch.chdir(dir_a)
        path_a = _copilot_instructions()

        monkeypatch.chdir(dir_b)
        path_b = _copilot_instructions()

        assert path_a != path_b, "Path was frozen at first call — module-level constant regression"
        assert str(dir_a.resolve()) in str(path_a)
        assert str(dir_b.resolve()) in str(path_b)

    def test_vscode_mcp_json_changes_with_cwd(self, tmp_path, monkeypatch):
        """Core regression test: path must re-resolve on every call."""
        dir_a = tmp_path / "dir_a"
        dir_b = tmp_path / "dir_b"
        dir_a.mkdir()
        dir_b.mkdir()

        monkeypatch.chdir(dir_a)
        path_a = _vscode_mcp_json()

        monkeypatch.chdir(dir_b)
        path_b = _vscode_mcp_json()

        assert path_a != path_b, "Path was frozen at first call — module-level constant regression"
        assert str(dir_a.resolve()) in str(path_a)
        assert str(dir_b.resolve()) in str(path_b)

    def test_copilot_instructions_path_ends_with_expected_suffix(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _copilot_instructions()
        assert result.parts[-1] == "copilot-instructions.md"
        assert result.parts[-2] == ".github"

    def test_vscode_mcp_json_path_ends_with_expected_suffix(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _vscode_mcp_json()
        assert result.parts[-1] == "mcp.json"
        assert result.parts[-2] == ".vscode"


# ---------------------------------------------------------------------------
# CopilotExtractor.extract_skills()
# ---------------------------------------------------------------------------


class TestExtractSkills:
    def _make_extractor(self):
        return CopilotExtractor()

    def test_returns_empty_when_file_absent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = self._make_extractor().extract_skills()
        assert result == []

    def test_reads_instructions_from_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        instr_dir = tmp_path / ".github"
        instr_dir.mkdir()
        (instr_dir / "copilot-instructions.md").write_text(
            "Always use TypeScript.", encoding="utf-8"
        )

        result = self._make_extractor().extract_skills()
        assert len(result) == 1
        assert result[0]["body"] == "Always use TypeScript."

    def test_source_tool_is_github_copilot(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "copilot-instructions.md").write_text("x")

        result = self._make_extractor().extract_skills()
        assert result[0]["source_tool"] == "github-copilot"

    def test_source_path_is_absolute(self, tmp_path, monkeypatch):
        """source_path in the extracted skill must be an absolute path (#42)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "copilot-instructions.md").write_text("rule")

        result = self._make_extractor().extract_skills()
        source_path = result[0]["source_path"]
        assert Path(source_path).is_absolute(), (
            f"source_path must be absolute, got: {source_path!r}"
        )

    def test_source_path_contains_cwd(self, tmp_path, monkeypatch):
        """source_path must be relative to the CWD at extraction time, not import time."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "copilot-instructions.md").write_text("rule")

        result = self._make_extractor().extract_skills()
        assert str(tmp_path.resolve()) in result[0]["source_path"]

    def test_checksum_present_and_prefixed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "copilot-instructions.md").write_text("rule")

        result = self._make_extractor().extract_skills()
        assert result[0]["checksum"].startswith("sha256:")

    def test_skill_name_is_copilot_instructions(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "copilot-instructions.md").write_text("rule")

        result = self._make_extractor().extract_skills()
        assert result[0]["name"] == "copilot-instructions"

    def test_reads_from_correct_dir_after_cwd_change(self, tmp_path, monkeypatch):
        """Extraction must use the CWD at call time, not at import time."""
        dir_a = tmp_path / "project_a"
        dir_b = tmp_path / "project_b"
        dir_a.mkdir()
        dir_b.mkdir()

        (dir_a / ".github").mkdir()
        (dir_a / ".github" / "copilot-instructions.md").write_text("project_a rules")
        (dir_b / ".github").mkdir()
        (dir_b / ".github" / "copilot-instructions.md").write_text("project_b rules")

        monkeypatch.chdir(dir_a)
        result_a = self._make_extractor().extract_skills()

        monkeypatch.chdir(dir_b)
        result_b = self._make_extractor().extract_skills()

        assert result_a[0]["body"] == "project_a rules"
        assert result_b[0]["body"] == "project_b rules"

    def test_returns_empty_on_ioerror(self, tmp_path, monkeypatch):
        """IOError during read must be swallowed, not propagated."""
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".github").mkdir()
        instr = tmp_path / ".github" / "copilot-instructions.md"
        instr.write_text("x")

        with patch("extractors.copilot._copilot_instructions", return_value=instr):
            with patch.object(Path, "read_text", side_effect=IOError("permission denied")):
                result = self._make_extractor().extract_skills()
        assert result == []


# ---------------------------------------------------------------------------
# CopilotExtractor.extract_mcp_servers()
# ---------------------------------------------------------------------------


class TestExtractMcpServers:
    def _make_extractor(self):
        return CopilotExtractor()

    def _write_mcp(self, tmp_path, data):
        vscode = tmp_path / ".vscode"
        vscode.mkdir(exist_ok=True)
        (vscode / "mcp.json").write_text(json.dumps(data), encoding="utf-8")

    def test_returns_empty_when_file_absent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = self._make_extractor().extract_mcp_servers()
        assert result == []

    def test_reads_servers_from_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._write_mcp(tmp_path, {"servers": {"my-mcp": {"command": "npx", "args": ["run"]}}})

        result = self._make_extractor().extract_mcp_servers()
        assert len(result) == 1
        assert result[0]["name"] == "my-mcp"

    def test_source_tool_is_github_copilot(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._write_mcp(tmp_path, {"servers": {"s": {"command": "x"}}})

        result = self._make_extractor().extract_mcp_servers()
        assert result[0]["source_tool"] == "github-copilot"

    def test_multiple_servers_extracted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._write_mcp(
            tmp_path,
            {
                "servers": {
                    "svc-a": {"command": "npx", "args": ["a"]},
                    "svc-b": {"command": "node", "args": ["b"]},
                }
            },
        )

        result = self._make_extractor().extract_mcp_servers()
        names = {r["name"] for r in result}
        assert names == {"svc-a", "svc-b"}

    def test_reads_from_correct_dir_after_cwd_change(self, tmp_path, monkeypatch):
        """MCP extraction must use CWD at call time, not import time."""
        dir_a = tmp_path / "proj_a"
        dir_b = tmp_path / "proj_b"
        dir_a.mkdir()
        dir_b.mkdir()

        self._write_mcp(dir_a, {"servers": {"mcp-a": {"command": "npx"}}})
        self._write_mcp(dir_b, {"servers": {"mcp-b": {"command": "node"}}})

        monkeypatch.chdir(dir_a)
        result_a = self._make_extractor().extract_mcp_servers()

        monkeypatch.chdir(dir_b)
        result_b = self._make_extractor().extract_mcp_servers()

        assert result_a[0]["name"] == "mcp-a"
        assert result_b[0]["name"] == "mcp-b"

    def test_malformed_json_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".vscode").mkdir()
        (tmp_path / ".vscode" / "mcp.json").write_text("{not valid json", encoding="utf-8")

        result = self._make_extractor().extract_mcp_servers()
        assert result == []

    def test_empty_servers_dict_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._write_mcp(tmp_path, {"servers": {}})

        result = self._make_extractor().extract_mcp_servers()
        assert result == []

    def test_missing_servers_key_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._write_mcp(tmp_path, {"mcpServers": {"s": {}}})  # wrong key format

        result = self._make_extractor().extract_mcp_servers()
        assert result == []

    def test_server_args_and_env_extracted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._write_mcp(
            tmp_path,
            {
                "servers": {
                    "my-svc": {
                        "command": "npx",
                        "args": ["--port", "8080"],
                        "env": {"TOKEN": "${SECRET}"},
                        "type": "stdio",
                    }
                }
            },
        )

        result = self._make_extractor().extract_mcp_servers()
        s = result[0]
        assert s["command"] == "npx"
        assert s["args"] == ["--port", "8080"]
        assert s["env"] == {"TOKEN": "${SECRET}"}
        assert s["transport"] == "stdio"


# ---------------------------------------------------------------------------
# CopilotExtractor.extract_memory()
# ---------------------------------------------------------------------------


class TestExtractMemory:
    def test_always_returns_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CopilotExtractor().extract_memory()
        assert result == []

    def test_returns_list_not_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CopilotExtractor().extract_memory()
        assert isinstance(result, list)
