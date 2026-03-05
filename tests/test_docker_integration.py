"""Docker integration tests — comprehensive CLI smoke tests with fake tool data.

Runs every apc command against seeded tool directories and verifies both
CLI output and file-system side effects (reads and writes).

Designed to run inside Docker (tests/Dockerfile) where HOME=/root and
CWD=/app, but also works locally via pytest with HOME override.
"""

import json
import shutil
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
        result = runner.invoke(cli, ["model", "status"])
        assert result.exit_code == 0, result.output

    def test_models_list_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["model", "list"])
        assert result.exit_code == 0, result.output

    def test_models_set(self, runner, cli):
        result = runner.invoke(cli, ["model", "set", "anthropic/claude-sonnet-4-6"])
        assert result.exit_code == 0
        # Verify it wrote to disk
        models_path = HOME / ".apc" / "models.json"
        assert models_path.exists()
        data = json.loads(models_path.read_text())
        assert data.get("default") == "anthropic/claude-sonnet-4-6"

    def test_models_set_invalid_format(self, runner, cli):
        result = runner.invoke(cli, ["model", "set", "no-slash"])
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
# Phase 11: apc install (network-dependent, graceful failure)
# ---------------------------------------------------------------------------


class TestInstall:
    def test_install_nonexistent_fails_gracefully(self, runner, cli):
        result = runner.invoke(cli, ["install", "test-nonexistent-skill-xyz"])
        # Should not crash — either exit 0 with "not found" message
        # or exit 1 but with a clean error message
        combined = result.output
        assert "not found" in combined.lower() or result.exit_code == 0


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


# ---------------------------------------------------------------------------
# Phase 13: apc export / apc import
# ---------------------------------------------------------------------------


class TestExport:
    @pytest.fixture(autouse=True)
    def _ensure_collected(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])

    @pytest.fixture
    def export_path(self, tmp_path):
        return tmp_path / "test-export"

    def test_export_exits_zero(self, runner, cli, export_path):
        result = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert result.exit_code == 0, result.output

    def test_export_creates_metadata(self, runner, cli, export_path):
        runner.invoke(cli, ["export", str(export_path), "--yes"])
        meta_path = export_path / "apc-export.json"
        assert meta_path.exists(), "apc-export.json not created"
        meta = json.loads(meta_path.read_text())
        assert meta["schema_version"] == 1
        assert "created_at" in meta
        assert "stats" in meta

    def test_export_creates_cache_files(self, runner, cli, export_path):
        runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert (export_path / "cache" / "skills.json").exists()
        assert (export_path / "cache" / "mcp_servers.json").exists()
        assert (export_path / "cache" / "memory.json").exists()

    def test_export_cache_has_data(self, runner, cli, export_path):
        runner.invoke(cli, ["export", str(export_path), "--yes"])

        skills = json.loads((export_path / "cache" / "skills.json").read_text())
        assert len(skills) > 0, "Exported skills.json is empty"

        mcp = json.loads((export_path / "cache" / "mcp_servers.json").read_text())
        assert len(mcp) > 0, "Exported mcp_servers.json is empty"

        memory = json.loads((export_path / "cache" / "memory.json").read_text())
        assert len(memory) > 0, "Exported memory.json is empty"

    def test_export_stats_match_cache(self, runner, cli, export_path):
        runner.invoke(cli, ["export", str(export_path), "--yes"])

        meta = json.loads((export_path / "apc-export.json").read_text())
        stats = meta["stats"]

        skills = json.loads((export_path / "cache" / "skills.json").read_text())
        mcp = json.loads((export_path / "cache" / "mcp_servers.json").read_text())
        memory = json.loads((export_path / "cache" / "memory.json").read_text())

        assert stats["skills"] == len(skills)
        assert stats["mcp_servers"] == len(mcp)
        assert stats["memory"] == len(memory)

    def test_export_no_secrets_flag(self, runner, cli, export_path):
        result = runner.invoke(cli, ["export", str(export_path), "--no-secrets", "--yes"])
        assert result.exit_code == 0, result.output

        meta = json.loads((export_path / "apc-export.json").read_text())
        assert meta["public_key"] is None

    def test_export_has_age_public_key(self, runner, cli, export_path):
        result = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert result.exit_code == 0, result.output

        meta = json.loads((export_path / "apc-export.json").read_text())
        # pyrage should be installed, so public key should be present
        assert meta["public_key"] is not None
        assert meta["public_key"].startswith("age1")

    def test_export_creates_age_identity(self, runner, cli, export_path):
        runner.invoke(cli, ["export", str(export_path), "--yes"])
        identity_path = HOME / ".apc" / "age-identity.txt"
        assert identity_path.exists(), "age-identity.txt not created"

    def test_export_idempotent(self, runner, cli, export_path):
        """Exporting twice to the same path should succeed (overwrite)."""
        r1 = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert r1.exit_code == 0
        r2 = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert r2.exit_code == 0

    def test_export_copies_config_files(self, runner, cli, export_path):
        """After configure, exported dir should contain config files."""
        # Set up auth profile and models
        runner.invoke(
            cli,
            ["configure", "--provider", "anthropic", "--api-key", "sk-test", "--non-interactive"],
        )
        runner.invoke(cli, ["export", str(export_path), "--yes"])

        assert (export_path / "config" / "models.json").exists()
        assert (export_path / "config" / "auth-profiles.json").exists()

    def test_export_encrypts_auth_profile_keys(self, runner, cli, export_path):
        """Auth profile keys should be encrypted in the export."""
        runner.invoke(
            cli,
            ["configure", "--provider", "openai", "--api-key", "sk-real-key", "--non-interactive"],
        )
        runner.invoke(cli, ["export", str(export_path), "--yes"])

        auth = json.loads((export_path / "config" / "auth-profiles.json").read_text())
        profile = auth["profiles"].get("openai:default", {})
        key_val = profile.get("key", "")
        assert key_val.startswith("AGE:"), f"Expected encrypted key, got: {key_val[:20]}"


class TestImport:
    @pytest.fixture(autouse=True)
    def _ensure_collected(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])

    @pytest.fixture
    def export_path(self, tmp_path):
        return tmp_path / "test-export"

    def _do_export(self, runner, cli, export_path):
        result = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert result.exit_code == 0, result.output

    def test_import_exits_zero(self, runner, cli, export_path):
        self._do_export(runner, cli, export_path)
        result = runner.invoke(cli, ["import", str(export_path), "--yes"])
        assert result.exit_code == 0, result.output

    def test_import_invalid_path(self, runner, cli, tmp_path):
        result = runner.invoke(cli, ["import", str(tmp_path / "nonexistent"), "--yes"])
        assert result.exit_code != 0

    def test_import_suggests_sync(self, runner, cli, export_path):
        self._do_export(runner, cli, export_path)
        result = runner.invoke(cli, ["import", str(export_path), "--yes"])
        assert "apc sync" in result.output

    def test_import_no_secrets_flag(self, runner, cli, export_path):
        self._do_export(runner, cli, export_path)
        result = runner.invoke(cli, ["import", str(export_path), "--no-secrets", "--yes"])
        assert result.exit_code == 0, result.output


class TestExportImportRoundTrip:
    """Full export → wipe → import → verify cycle."""

    @pytest.fixture(autouse=True)
    def _ensure_collected(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        # Add a manual memory entry to test persistence
        runner.invoke(cli, ["memory", "add", "Round-trip test memory", "--category", "preference"])

    @pytest.fixture
    def export_path(self, tmp_path):
        return tmp_path / "roundtrip-export"

    def test_round_trip_preserves_skills(self, runner, cli, export_path):
        """Export, wipe cache, import, verify skills restored."""
        # Export
        r = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert r.exit_code == 0

        # Record original skills
        orig = json.loads((HOME / ".apc" / "cache" / "skills.json").read_text())
        orig_names = sorted(s.get("name") for s in orig)

        # Wipe cache skills
        (HOME / ".apc" / "cache" / "skills.json").write_text("[]")

        # Import
        r = runner.invoke(cli, ["import", str(export_path), "--yes"])
        assert r.exit_code == 0

        # Verify
        restored = json.loads((HOME / ".apc" / "cache" / "skills.json").read_text())
        restored_names = sorted(s.get("name") for s in restored)
        assert restored_names == orig_names

    def test_round_trip_preserves_mcp_servers(self, runner, cli, export_path):
        """Export, wipe cache, import, verify MCP servers restored."""
        r = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert r.exit_code == 0

        orig = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        orig_names = sorted(s.get("name") for s in orig)

        (HOME / ".apc" / "cache" / "mcp_servers.json").write_text("[]")

        r = runner.invoke(cli, ["import", str(export_path), "--yes"])
        assert r.exit_code == 0

        restored = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        restored_names = sorted(s.get("name") for s in restored)
        assert restored_names == orig_names

    def test_round_trip_preserves_memory(self, runner, cli, export_path):
        """Export, wipe cache, import, verify memory restored including manual entry."""
        r = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert r.exit_code == 0

        (HOME / ".apc" / "cache" / "memory.json").write_text("[]")

        r = runner.invoke(cli, ["import", str(export_path), "--yes"])
        assert r.exit_code == 0

        restored = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        contents = [e.get("content", "") for e in restored]
        assert "Round-trip test memory" in contents

    def test_round_trip_preserves_config(self, runner, cli, export_path):
        """Export with auth profile, wipe, import, verify config restored."""
        # Set up auth
        runner.invoke(
            cli,
            [
                "configure",
                "--provider",
                "anthropic",
                "--api-key",
                "sk-roundtrip",
                "--non-interactive",
            ],
        )

        r = runner.invoke(cli, ["export", str(export_path), "--yes"])
        assert r.exit_code == 0

        # Wipe auth profiles
        auth_path = HOME / ".apc" / "auth-profiles.json"
        auth_path.write_text(json.dumps({"version": 1, "profiles": {}, "order": {}}))

        r = runner.invoke(cli, ["import", str(export_path), "--yes"])
        assert r.exit_code == 0

        # Verify auth profile was restored (key should be decrypted)
        data = json.loads(auth_path.read_text())
        profile = data.get("profiles", {}).get("anthropic:default", {})
        assert profile.get("key") == "sk-roundtrip"

    def test_status_after_round_trip(self, runner, cli, export_path):
        """After export → wipe → import, apc status should still work."""
        runner.invoke(cli, ["export", str(export_path), "--yes"])

        # Wipe all cache
        cache_dir = HOME / ".apc" / "cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            cache_dir.mkdir()

        runner.invoke(cli, ["import", str(export_path), "--yes"])

        r = runner.invoke(cli, ["status"])
        assert r.exit_code == 0
