"""Docker integration tests — comprehensive CLI smoke tests with fake tool data.

Runs every apc command against seeded tool directories and verifies both
CLI output and file-system side effects (reads and writes).

Designed to run inside Docker (tests/Dockerfile) where HOME=/root and
CWD=/app, but also works locally via pytest with HOME override.
"""

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HOME = Path.home()


@pytest.fixture(autouse=True, scope="session")
def seed_tool_data():
    """Create fake tool directories and data files before any test runs."""

    # ── Claude Code ──────────────────────────────────────────────────────
    commands_dir = HOME / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    (commands_dir / "test-skill.md").write_text(
        textwrap.dedent("""\
            ---
            name: test-skill
            description: A test skill for Docker integration
            tags:
              - test
            version: "1.0.0"
            ---

            This is a test skill body for integration testing.
        """)
    )

    claude_json = HOME / ".claude.json"
    claude_json.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "test-claude-mcp": {
                        "type": "stdio",
                        "command": "echo",
                        "args": ["hello"],
                    }
                }
            },
            indent=2,
        )
    )

    claude_md = HOME / ".claude" / "CLAUDE.md"
    claude_md.write_text("# Test Memory\nThis is test memory content for Claude.\n")

    # ── Cursor ───────────────────────────────────────────────────────────
    cursor_dir = HOME / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    (cursor_dir / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "test-cursor-mcp": {
                        "type": "stdio",
                        "command": "echo",
                        "args": ["cursor"],
                    }
                }
            },
            indent=2,
        )
    )

    # ── Gemini CLI ───────────────────────────────────────────────────────
    gemini_dir = HOME / ".gemini"
    gemini_dir.mkdir(parents=True, exist_ok=True)
    (gemini_dir / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "test-gemini-mcp": {
                        "type": "stdio",
                        "command": "echo",
                        "args": ["gemini"],
                    }
                }
            },
            indent=2,
        )
    )

    # ── GitHub Copilot (relative paths from CWD) ─────────────────────────
    (HOME / ".github").mkdir(parents=True, exist_ok=True)
    (HOME / ".copilot").mkdir(parents=True, exist_ok=True)

    vscode_dir = Path.cwd() / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    (vscode_dir / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "test-copilot-mcp": {
                        "type": "stdio",
                        "command": "echo",
                        "args": ["copilot"],
                    }
                }
            },
            indent=2,
        )
    )

    # ── Windsurf ─────────────────────────────────────────────────────────
    windsurf_dir = HOME / ".codeium" / "windsurf"
    windsurf_dir.mkdir(parents=True, exist_ok=True)
    (windsurf_dir / "mcp_config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "test-windsurf-mcp": {
                        "type": "stdio",
                        "command": "echo",
                        "args": ["windsurf"],
                    }
                }
            },
            indent=2,
        )
    )

    # ── OpenClaw ─────────────────────────────────────────────────────────
    oc_skill_dir = HOME / ".openclaw" / "skills" / "oc-skill"
    oc_skill_dir.mkdir(parents=True, exist_ok=True)
    (oc_skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
            ---
            name: oc-skill
            description: An OpenClaw test skill
            tags:
              - test
            version: "1.0.0"
            ---

            OpenClaw test skill body.
        """)
    )

    workspace_dir = HOME / ".openclaw" / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "USER.md").write_text("# OpenClaw User\nTest user memory for OpenClaw.\n")


@pytest.fixture
def runner():
    """Provide a Click CliRunner."""
    return CliRunner()


@pytest.fixture
def cli():
    """Import and return the CLI group."""
    from main import cli as _cli

    return _cli


# ---------------------------------------------------------------------------
# Phase 2: apc status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0, result.output

    def test_detects_claude(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "claude" in result.output.lower()

    def test_detects_cursor(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "cursor" in result.output.lower()

    def test_detects_gemini(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "gemini" in result.output.lower()

    def test_detects_copilot(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "copilot" in result.output.lower()

    def test_detects_windsurf(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "windsurf" in result.output.lower()

    def test_detects_openclaw(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "openclaw" in result.output.lower()


# ---------------------------------------------------------------------------
# Phase 3: apc collect
# ---------------------------------------------------------------------------


class TestCollect:
    def test_collect_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["collect", "--yes"])
        assert result.exit_code == 0, result.output

    def test_cache_skills_json_created(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        path = HOME / ".apc" / "cache" / "skills.json"
        assert path.exists(), "skills.json not created"

    def test_cache_mcp_servers_json_created(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        path = HOME / ".apc" / "cache" / "mcp_servers.json"
        assert path.exists(), "mcp_servers.json not created"

    def test_cache_memory_json_created(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        path = HOME / ".apc" / "cache" / "memory.json"
        assert path.exists(), "memory.json not created"

    def test_skills_json_has_entries(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "skills.json").read_text())
        assert len(data) > 0, "skills.json is empty"

    def test_mcp_servers_json_has_entries(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        # 5 tools have MCP: claude, cursor, gemini, copilot, windsurf
        assert len(data) >= 5, f"Expected >= 5 MCP servers, got {len(data)}"

    def test_memory_json_has_entries(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        assert len(data) > 0, "memory.json is empty"

    def test_skills_contain_test_skill(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "skills.json").read_text())
        names = [s.get("name") for s in data]
        assert "test-skill" in names, f"test-skill not found in {names}"

    def test_skills_contain_oc_skill(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "skills.json").read_text())
        names = [s.get("name") for s in data]
        assert "oc-skill" in names, f"oc-skill not found in {names}"

    def test_mcp_servers_have_correct_source_tools(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        sources = {s.get("source_tool") for s in data}
        expected = {"claude", "cursor", "gemini", "copilot", "windsurf"}
        assert expected.issubset(sources), f"Missing sources: {expected - sources}"

    def test_memory_has_claude_entry(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        sources = {e.get("source_tool") for e in data}
        assert "claude" in sources

    def test_memory_has_openclaw_entry(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        sources = {e.get("source_tool") for e in data}
        assert "openclaw" in sources

    def test_collect_with_tool_filter(self, runner, cli):
        result = runner.invoke(cli, ["collect", "--tools", "claude-code", "--yes"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Phase 4: apc skill list / show
# ---------------------------------------------------------------------------


class TestSkill:
    @pytest.fixture(autouse=True)
    def _ensure_collected(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])

    def test_skill_list_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["skill", "list"])
        assert result.exit_code == 0, result.output

    def test_skill_list_shows_test_skill(self, runner, cli):
        result = runner.invoke(cli, ["skill", "list"])
        assert "test-skill" in result.output

    def test_skill_list_shows_oc_skill(self, runner, cli):
        result = runner.invoke(cli, ["skill", "list"])
        assert "oc-skill" in result.output

    def test_skill_show_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["skill", "show"])
        assert result.exit_code == 0, result.output

    def test_skill_show_by_name(self, runner, cli):
        result = runner.invoke(cli, ["skill", "show", "test-skill"])
        assert result.exit_code == 0
        assert "test skill" in result.output.lower() or "test-skill" in result.output.lower()


# ---------------------------------------------------------------------------
# Phase 5: apc memory commands
# ---------------------------------------------------------------------------


class TestMemory:
    @pytest.fixture(autouse=True)
    def _ensure_collected(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])

    def test_memory_list_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0, result.output

    def test_memory_add_exits_zero(self, runner, cli):
        result = runner.invoke(
            cli, ["memory", "add", "Docker test pref", "--category", "preference"]
        )
        assert result.exit_code == 0, result.output

    def test_memory_add_persists(self, runner, cli):
        runner.invoke(cli, ["memory", "add", "Docker test pref", "--category", "preference"])
        result = runner.invoke(cli, ["memory", "list"])
        assert "Docker test pref" in result.output

    def test_memory_add_writes_to_cache(self, runner, cli):
        runner.invoke(cli, ["memory", "add", "Unique docker mem", "--category", "workflow"])
        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        contents = [e.get("content", "") for e in data]
        assert "Unique docker mem" in contents

    def test_memory_show_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["memory", "show"])
        assert result.exit_code == 0, result.output

    def test_memory_list_shows_collected_files(self, runner, cli):
        result = runner.invoke(cli, ["memory", "list"])
        # Should show raw-file entries from claude and openclaw
        assert "claude" in result.output.lower() or "openclaw" in result.output.lower()


# ---------------------------------------------------------------------------
# Phase 6: apc mcp commands
# ---------------------------------------------------------------------------


class TestMcp:
    @pytest.fixture(autouse=True)
    def _ensure_collected(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])

    def test_mcp_list_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["mcp", "list"])
        assert result.exit_code == 0, result.output

    def test_mcp_list_shows_servers(self, runner, cli):
        result = runner.invoke(cli, ["mcp", "list"])
        assert "test-claude-mcp" in result.output

    def test_mcp_remove_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["mcp", "remove", "test-claude-mcp", "-y"])
        assert result.exit_code == 0, result.output

    def test_mcp_remove_deletes_from_cache(self, runner, cli):
        runner.invoke(cli, ["mcp", "remove", "test-claude-mcp", "-y"])
        data = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        names = [s.get("name") for s in data]
        assert "test-claude-mcp" not in names

    def test_mcp_remove_nonexistent(self, runner, cli):
        result = runner.invoke(cli, ["mcp", "remove", "no-such-server", "-y"])
        assert result.exit_code == 0  # exits 0 with warning
        assert "no mcp server" in result.output.lower() or "not found" in result.output.lower()

    def test_mcp_list_after_remove(self, runner, cli):
        runner.invoke(cli, ["mcp", "remove", "test-claude-mcp", "-y"])
        result = runner.invoke(cli, ["mcp", "list"])
        assert "test-claude-mcp" not in result.output
        # Other servers should still be there
        assert "test-cursor-mcp" in result.output


# ---------------------------------------------------------------------------
# Phase 7: apc sync
# ---------------------------------------------------------------------------


class TestSync:
    @pytest.fixture(autouse=True)
    def _ensure_collected(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])

    def test_sync_to_claude_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["sync", "--tools", "claude-code", "--yes", "--no-memory"])
        assert result.exit_code == 0, result.output

    def test_sync_writes_claude_json_mcp(self, runner, cli):
        runner.invoke(cli, ["sync", "--tools", "claude-code", "--yes", "--no-memory"])
        data = json.loads((HOME / ".claude.json").read_text())
        assert "mcpServers" in data
        # Should have synced MCP servers from cache
        assert len(data["mcpServers"]) > 0

    def test_sync_writes_claude_skill_files(self, runner, cli):
        runner.invoke(cli, ["sync", "--tools", "claude-code", "--yes", "--no-memory"])
        commands_dir = HOME / ".claude" / "commands"
        skill_files = list(commands_dir.glob("*.md"))
        assert len(skill_files) > 0, "No skill files written to claude commands dir"

    def test_sync_to_cursor_exits_zero(self, runner, cli):
        result = runner.invoke(
            cli, ["sync", "--tools", "cursor", "--yes", "--no-memory", "--override-mcp"]
        )
        assert result.exit_code == 0, result.output

    def test_sync_writes_cursor_mcp(self, runner, cli):
        runner.invoke(cli, ["sync", "--tools", "cursor", "--yes", "--no-memory", "--override-mcp"])
        data = json.loads((HOME / ".cursor" / "mcp.json").read_text())
        assert "mcpServers" in data
        assert len(data["mcpServers"]) > 0

    def test_sync_dry_run(self, runner, cli):
        result = runner.invoke(cli, ["sync", "--dry-run", "--all", "--yes"])
        assert result.exit_code == 0
        assert "no files written" in result.output.lower()

    def test_sync_dry_run_does_not_modify_files(self, runner, cli):
        # Record state before
        claude_json_before = (HOME / ".claude.json").read_text()
        runner.invoke(cli, ["sync", "--dry-run", "--all", "--yes"])
        claude_json_after = (HOME / ".claude.json").read_text()
        assert claude_json_before == claude_json_after


# ---------------------------------------------------------------------------
# Phase 8: apc mcp sync / apc skill sync
# ---------------------------------------------------------------------------


class TestSubSync:
    @pytest.fixture(autouse=True)
    def _ensure_collected(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])

    def test_mcp_sync_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["mcp", "sync", "--tools", "claude-code", "--yes"])
        assert result.exit_code == 0, result.output

    def test_mcp_sync_writes_servers(self, runner, cli):
        runner.invoke(cli, ["mcp", "sync", "--tools", "claude-code", "--yes"])
        data = json.loads((HOME / ".claude.json").read_text())
        assert "mcpServers" in data
        assert len(data["mcpServers"]) > 0

    def test_skill_sync_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["skill", "sync", "--tools", "claude-code", "--yes"])
        assert result.exit_code == 0, result.output

    def test_skill_sync_writes_skill_files(self, runner, cli):
        runner.invoke(cli, ["skill", "sync", "--tools", "claude-code", "--yes"])
        commands_dir = HOME / ".claude" / "commands"
        skill_files = list(commands_dir.glob("*.md"))
        assert len(skill_files) > 0


# ---------------------------------------------------------------------------
# Phase 9: apc models
# ---------------------------------------------------------------------------


class TestModels:
    def test_models_status_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["models", "status"])
        assert result.exit_code == 0, result.output

    def test_models_list_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["models", "list"])
        assert result.exit_code == 0, result.output

    def test_models_set(self, runner, cli):
        result = runner.invoke(cli, ["models", "set", "anthropic/claude-sonnet-4-6"])
        assert result.exit_code == 0
        # Verify it wrote to disk
        models_path = HOME / ".apc" / "models.json"
        assert models_path.exists()
        data = json.loads(models_path.read_text())
        assert data.get("default") == "anthropic/claude-sonnet-4-6"

    def test_models_set_invalid_format(self, runner, cli):
        result = runner.invoke(cli, ["models", "set", "no-slash"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Phase 10: apc configure (non-interactive)
# ---------------------------------------------------------------------------


class TestConfigure:
    def test_configure_non_interactive(self, runner, cli):
        result = runner.invoke(
            cli,
            [
                "configure",
                "--provider",
                "anthropic",
                "--api-key",
                "sk-test-key",
                "--non-interactive",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_configure_writes_auth_profile(self, runner, cli):
        runner.invoke(
            cli,
            [
                "configure",
                "--provider",
                "openai",
                "--api-key",
                "sk-test-openai",
                "--non-interactive",
            ],
        )
        path = HOME / ".apc" / "auth-profiles.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "openai:default" in data.get("profiles", {})

    def test_configure_writes_models_json(self, runner, cli):
        runner.invoke(
            cli,
            [
                "configure",
                "--provider",
                "anthropic",
                "--api-key",
                "sk-test-key",
                "--non-interactive",
            ],
        )
        path = HOME / ".apc" / "models.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "anthropic" in data.get("providers", {})


# ---------------------------------------------------------------------------
# Phase 11: apc install (GitHub repo-first UX)
# ---------------------------------------------------------------------------


class TestInstall:
    """Tests for apc install — repo-first GitHub skill installation."""

    def test_install_invalid_repo_format(self, runner, cli):
        """Non-slug repos are rejected with a clear error."""
        result = runner.invoke(cli, ["install", "https://github.com/owner/repo"])
        assert result.exit_code != 0
        assert "owner/repo slug" in result.output.lower() or "usage error" in result.output.lower()

    def test_install_invalid_no_slash(self, runner, cli):
        """Repo without a slash is rejected."""
        result = runner.invoke(cli, ["install", "notaslug"])
        assert result.exit_code != 0

    def test_install_list_mocked(self, runner, cli, monkeypatch):
        """--list prints available skills from the repo."""
        from unittest.mock import patch

        mock_skills = ["frontend-design", "skill-creator", "pdf"]

        with patch("share.list_skills_in_repo", return_value=mock_skills):
            result = runner.invoke(cli, ["install", "owner/repo", "--list"])

        assert result.exit_code == 0
        assert "frontend-design" in result.output
        assert "skill-creator" in result.output
        assert "pdf" in result.output
        assert "3 skill(s) found" in result.output

    def test_install_list_empty_repo(self, runner, cli):
        """--list on a repo with no skills prints an error."""
        from unittest.mock import patch

        with patch("share.list_skills_in_repo", return_value=[]):
            result = runner.invoke(cli, ["install", "owner/repo", "--list"])

        assert "no skills found" in result.output.lower()

    def test_install_single_skill_mocked(self, runner, cli, monkeypatch):
        """Installing a single skill fetches, saves to cache, and applies to agents."""
        from unittest.mock import patch

        mock_skill = {
            "name": "frontend-design",
            "description": "Frontend design skill",
            "body": "Frontend skill body.",
            "tags": ["design"],
            "targets": [],
            "version": "1.0.0",
            "source_tool": "github",
            "source_repo": "owner/repo",
            "_raw_content": "---\nname: frontend-design\n---\nFrontend skill body.",
        }

        with (
            patch("share.fetch_skill_from_repo", return_value=mock_skill),
            patch("share._apply_skill_to_agents", return_value=1),
        ):
            result = runner.invoke(
                cli,
                ["install", "owner/repo", "--skill", "frontend-design", "-a", "cursor", "-y"],
            )

        assert result.exit_code == 0
        assert "✓" in result.output
        assert "frontend-design" in result.output

    def test_install_skill_not_found(self, runner, cli):
        """A skill that doesn't exist in the repo prints a clear not-found message."""
        from unittest.mock import patch

        with patch("share.fetch_skill_from_repo", return_value=None):
            result = runner.invoke(
                cli,
                ["install", "owner/repo", "--skill", "nonexistent-skill", "-a", "cursor", "-y"],
            )

        assert (
            "not found" in result.output.lower()
            or "no skills were installed" in result.output.lower()
        )

    def test_install_all_mocked(self, runner, cli):
        """--all fetches and installs every skill in the repo."""
        from unittest.mock import patch

        skill_names = ["skill-a", "skill-b"]

        def fake_fetch(repo, name, branch="main"):
            return {
                "name": name,
                "description": "",
                "body": f"{name} body",
                "tags": [],
                "targets": [],
                "version": "1.0.0",
                "source_tool": "github",
                "source_repo": repo,
                "_raw_content": f"---\nname: {name}\n---\n{name} body",
            }

        with (
            patch("share.list_skills_in_repo", return_value=skill_names),
            patch("share.fetch_skill_from_repo", side_effect=fake_fetch),
            patch("share._apply_skill_to_agents", return_value=1),
        ):
            result = runner.invoke(cli, ["install", "owner/repo", "--all", "-a", "cursor", "-y"])

        assert result.exit_code == 0
        assert "2 skill(s)" in result.output

    def test_install_yes_flag_skips_confirmation(self, runner, cli):
        """The -y flag proceeds without interactive prompts."""
        from unittest.mock import patch

        mock_skill = {
            "name": "test-skill",
            "description": "",
            "body": "body",
            "tags": [],
            "targets": [],
            "version": "1.0.0",
            "source_tool": "github",
            "source_repo": "owner/repo",
            "_raw_content": "---\nname: test-skill\n---\nbody",
        }

        with (
            patch("share.fetch_skill_from_repo", return_value=mock_skill),
            patch("share._apply_skill_to_agents", return_value=1),
        ):
            result = runner.invoke(
                cli, ["install", "owner/repo", "-s", "test-skill", "-a", "cursor", "-y"]
            )

        # Should complete without asking any questions
        assert result.exit_code == 0
        assert "Proceed?" not in result.output


# ---------------------------------------------------------------------------
# Phase 12: Full round-trip — collect → sync → verify files
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Verify the full collect → sync → read-back cycle."""

    def test_collect_then_sync_claude(self, runner, cli):
        """Collect from all tools, sync to claude, verify files written."""
        # Collect
        r = runner.invoke(cli, ["collect", "--yes"])
        assert r.exit_code == 0

        # Sync to claude
        r = runner.invoke(cli, ["sync", "--tools", "claude-code", "--yes", "--no-memory"])
        assert r.exit_code == 0

        # Verify MCP servers in claude.json include servers from other tools
        data = json.loads((HOME / ".claude.json").read_text())
        mcp_names = set(data.get("mcpServers", {}).keys())
        # Should have cursor, gemini, copilot, windsurf MCP servers synced
        for expected in ["test-cursor-mcp", "test-gemini-mcp", "test-windsurf-mcp"]:
            assert expected in mcp_names, f"{expected} not found in claude.json mcpServers"

    def test_collect_then_sync_cursor_override(self, runner, cli):
        """Collect, sync to cursor with --override-mcp, verify only cache servers remain."""
        r = runner.invoke(cli, ["collect", "--yes"])
        assert r.exit_code == 0

        r = runner.invoke(
            cli, ["sync", "--tools", "cursor", "--yes", "--no-memory", "--override-mcp"]
        )
        assert r.exit_code == 0

        data = json.loads((HOME / ".cursor" / "mcp.json").read_text())
        mcp_names = set(data.get("mcpServers", {}).keys())
        # With override, only the cache servers should be present
        assert len(mcp_names) > 0

    def test_mcp_remove_then_resync(self, runner, cli):
        """Remove an MCP server from cache, re-collect, verify it's back."""
        runner.invoke(cli, ["collect", "--yes"])

        # Remove from cache
        runner.invoke(cli, ["mcp", "remove", "test-claude-mcp", "-y"])
        data = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        names = [s.get("name") for s in data]
        assert "test-claude-mcp" not in names

        # Re-collect should bring it back
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        names = [s.get("name") for s in data]
        assert "test-claude-mcp" in names

    def test_memory_add_persists_across_collect(self, runner, cli):
        """Manually added memory should survive a re-collect (merge, not replace)."""
        runner.invoke(cli, ["collect", "--yes"])
        runner.invoke(cli, ["memory", "add", "Persist across collect", "--category", "preference"])

        # Re-collect
        runner.invoke(cli, ["collect", "--yes"])

        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        contents = [e.get("content", "") for e in data]
        assert "Persist across collect" in contents
