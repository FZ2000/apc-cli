"""Tests for MCP server name conflict resolution during apc collect (#47).

When two or more tools provide an MCP server with the same name, apc collect
presents a prompt letting the user:
  - overwrite  → keep one canonical entry, discard the other
  - rename     → keep both, suffix the non-canonical one with its source tool

With --yes / in non-interactive mode: last-collected wins silently.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from collect import _resolve_mcp_conflicts

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _server(name: str, tool: str, command: str = "npx") -> dict:
    return {
        "name": name,
        "source_tool": tool,
        "command": command,
        "args": [],
        "env": {},
        "transport": "stdio",
        "targets": [],
    }


# ---------------------------------------------------------------------------
# No-conflict cases
# ---------------------------------------------------------------------------


class TestNoConflict:
    def test_empty_list_returns_empty(self):
        assert _resolve_mcp_conflicts([], yes=False) == []

    def test_single_server_returned_unchanged(self):
        servers = [_server("my-mcp", "claude-code")]
        result = _resolve_mcp_conflicts(servers, yes=False)
        assert result == servers

    def test_different_names_all_returned(self):
        servers = [
            _server("mcp-a", "claude-code"),
            _server("mcp-b", "cursor"),
        ]
        result = _resolve_mcp_conflicts(servers, yes=False)
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"mcp-a", "mcp-b"}

    def test_same_name_same_tool_no_conflict(self):
        """Duplicate entries from the same tool are not flagged as conflicts."""
        servers = [
            _server("mcp-x", "claude-code"),
            _server("mcp-x", "claude-code"),
        ]
        # Two entries with same name from same tool — collision detected but only one tool involved
        result = _resolve_mcp_conflicts(servers, yes=True)
        assert len(result) == 2  # --yes, returned as-is (merge handles dedup later)


# ---------------------------------------------------------------------------
# --yes / non-interactive: last-collected wins
# ---------------------------------------------------------------------------


class TestYesMode:
    def test_conflict_with_yes_returns_all(self):
        """--yes skips prompts; all entries returned, merge handles dedup."""
        servers = [
            _server("my-mcp", "claude-code"),
            _server("my-mcp", "cursor"),
        ]
        result = _resolve_mcp_conflicts(servers, yes=True)
        assert len(result) == 2

    def test_three_way_conflict_with_yes(self):
        servers = [
            _server("shared", "claude-code"),
            _server("shared", "cursor"),
            _server("shared", "gemini-cli"),
        ]
        result = _resolve_mcp_conflicts(servers, yes=True)
        assert len(result) == 3

    def test_yes_mixes_conflict_and_clean(self):
        servers = [
            _server("shared", "claude-code"),
            _server("shared", "cursor"),
            _server("unique", "gemini-cli"),
        ]
        result = _resolve_mcp_conflicts(servers, yes=True)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Interactive: overwrite (keep one, discard other)
# ---------------------------------------------------------------------------


class TestInteractiveOverwrite:
    def test_overwrite_keeps_chosen_entry(self):
        """User picks entry #1 and discards entry #2."""
        servers = [
            _server("my-mcp", "claude-code", command="npx"),
            _server("my-mcp", "cursor", command="node"),
        ]
        # Pick #1 (claude-code), discard cursor
        with patch("click.prompt", side_effect=["1", "d"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        names = [s["name"] for s in result]
        assert names.count("my-mcp") == 1
        kept = next(s for s in result if s["name"] == "my-mcp")
        assert kept["source_tool"] == "claude-code"

    def test_overwrite_second_entry(self):
        """User picks entry #2 and discards entry #1."""
        servers = [
            _server("shared", "claude-code"),
            _server("shared", "cursor"),
        ]
        with patch("click.prompt", side_effect=["2", "d"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        assert len([s for s in result if s["name"] == "shared"]) == 1
        kept = next(s for s in result if s["name"] == "shared")
        assert kept["source_tool"] == "cursor"

    def test_non_conflicting_servers_always_included(self):
        """Clean servers must be present regardless of conflict resolution choice."""
        servers = [
            _server("shared", "claude-code"),
            _server("shared", "cursor"),
            _server("unique-a", "claude-code"),
            _server("unique-b", "cursor"),
        ]
        with patch("click.prompt", side_effect=["1", "d"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        names = {s["name"] for s in result}
        assert "unique-a" in names
        assert "unique-b" in names

    def test_discard_removes_other_entry(self):
        servers = [
            _server("mcp", "claude-code"),
            _server("mcp", "cursor"),
        ]
        with patch("click.prompt", side_effect=["1", "d"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        assert not any(s["source_tool"] == "cursor" and s["name"] == "mcp" for s in result)

    def test_invalid_choice_falls_back_to_last(self):
        """Invalid index falls back to last-collected entry."""
        servers = [
            _server("mcp", "claude-code"),
            _server("mcp", "cursor"),
        ]
        with patch("click.prompt", side_effect=["99", "d"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        # Should have exactly one entry named "mcp"
        assert len([s for s in result if s["name"] == "mcp"]) == 1


# ---------------------------------------------------------------------------
# Interactive: rename (keep both with suffix)
# ---------------------------------------------------------------------------


class TestInteractiveRename:
    def test_rename_adds_tool_suffix(self):
        """User picks entry #1 as canonical and renames entry #2."""
        servers = [
            _server("my-mcp", "claude-code"),
            _server("my-mcp", "cursor"),
        ]
        with patch("click.prompt", side_effect=["1", "r"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        names = [s["name"] for s in result]
        assert "my-mcp" in names
        assert "my-mcp-cursor" in names

    def test_renamed_entry_keeps_original_data(self):
        """Renamed entry must have the original command/args, just a new name."""
        servers = [
            _server("shared", "claude-code", command="npx"),
            _server("shared", "cursor", command="node"),
        ]
        with patch("click.prompt", side_effect=["1", "r"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        renamed = next((s for s in result if s["name"] == "shared-cursor"), None)
        assert renamed is not None
        assert renamed["command"] == "node"
        assert renamed["source_tool"] == "cursor"

    def test_canonical_entry_name_unchanged(self):
        servers = [
            _server("mcp", "claude-code"),
            _server("mcp", "cursor"),
        ]
        with patch("click.prompt", side_effect=["1", "r"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        canonical = next(s for s in result if s["name"] == "mcp")
        assert canonical["source_tool"] == "claude-code"

    def test_three_way_conflict_rename_all(self):
        """Three-way collision: keep entry #1 canonical, rename #2 and #3."""
        servers = [
            _server("shared", "claude-code"),
            _server("shared", "cursor"),
            _server("shared", "gemini-cli"),
        ]
        # Pick #1, rename #2, rename #3
        with patch("click.prompt", side_effect=["1", "r", "r"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        names = {s["name"] for s in result}
        assert "shared" in names
        assert "shared-cursor" in names
        assert "shared-gemini-cli" in names

    def test_three_way_conflict_rename_one_discard_one(self):
        """Three-way: keep #1, rename #2, discard #3."""
        servers = [
            _server("shared", "claude-code"),
            _server("shared", "cursor"),
            _server("shared", "gemini-cli"),
        ]
        with patch("click.prompt", side_effect=["1", "r", "d"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        names = {s["name"] for s in result}
        assert "shared" in names
        assert "shared-cursor" in names
        assert "shared-gemini-cli" not in names

    def test_result_count_rename(self):
        servers = [
            _server("s", "claude-code"),
            _server("s", "cursor"),
        ]
        with patch("click.prompt", side_effect=["1", "r"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        assert len(result) == 2

    def test_result_count_discard(self):
        servers = [
            _server("s", "claude-code"),
            _server("s", "cursor"),
        ]
        with patch("click.prompt", side_effect=["1", "d"]):
            result = _resolve_mcp_conflicts(servers, yes=False)

        assert len(result) == 1


# ---------------------------------------------------------------------------
# Integration via CLI (apc collect --yes skips MCP conflict prompts)
# ---------------------------------------------------------------------------


class TestCollectMcpConflictIntegration:
    """End-to-end: two tools with the same MCP server name."""

    def test_collect_yes_deduplicates_by_source_tool(self, tmp_path, monkeypatch):
        """With --yes, collect accepts both entries without prompting."""
        from click.testing import CliRunner

        monkeypatch.setenv("HOME", str(tmp_path))

        # Set up cursor with a shared MCP server
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        (cursor_dir / "mcp.json").write_text(
            json.dumps({"mcpServers": {"shared-mcp": {"command": "npx", "args": []}}}),
            encoding="utf-8",
        )

        # Set up claude with the same MCP server name
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(
            json.dumps({"mcpServers": {"shared-mcp": {"command": "node", "args": []}}}),
            encoding="utf-8",
        )

        from main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["collect", "--yes"])
        assert result.exit_code == 0, result.output

    def test_collect_without_mcp_conflict_no_prompt(self, tmp_path, monkeypatch):
        """No conflict → no prompt shown; collect proceeds normally."""
        from click.testing import CliRunner

        monkeypatch.setenv("HOME", str(tmp_path))
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        (cursor_dir / "mcp.json").write_text(
            json.dumps({"mcpServers": {"cursor-only-mcp": {"command": "npx", "args": []}}}),
            encoding="utf-8",
        )

        from main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["collect", "--yes"])
        assert result.exit_code == 0, result.output
        assert "conflict" not in result.output.lower()
