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
        assert (HOME / ".claude").is_dir()

    def test_detects_cursor(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "cursor" in result.output.lower()
        assert (HOME / ".cursor").is_dir()

    def test_detects_gemini(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "gemini" in result.output.lower()
        assert (HOME / ".gemini").is_dir()

    def test_detects_copilot(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "copilot" in result.output.lower()

    def test_detects_windsurf(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "windsurf" in result.output.lower()
        assert (HOME / ".codeium" / "windsurf").is_dir()

    def test_detects_openclaw(self, runner, cli):
        result = runner.invoke(cli, ["status"])
        assert "openclaw" in result.output.lower()
        assert (HOME / ".openclaw").is_dir()

    # ------------------------------------------------------------------
    # Parametrized sync-status tests — cover every supported tool so
    # TOOL_NAME mismatches are caught (TOOL_NAME must equal the detected name).
    # ------------------------------------------------------------------

    # (detected_name, seed_dirs, applier_tool_name, mcp_file, mcp_key, supports_skills)
    # seed_dirs: list of relative paths to mkdir under tmp_path
    # mcp_file:  relative path to the MCP JSON file for this tool (or None)
    # mcp_key:   top-level JSON key for MCP servers in that file
    # supports_skills: whether apply_skills() writes files (vs returning 0)
    _TOOL_PARAMS = [
        pytest.param(
            "cursor",
            [".cursor"],
            "cursor",
            ".cursor/mcp.json",
            "mcpServers",
            True,
            id="cursor",
        ),
        pytest.param(
            "claude-code",
            [".claude"],  # .claude.json is a file, not a dir — created by apply_mcp_servers
            "claude-code",
            ".claude.json",
            "mcpServers",
            True,
            id="claude-code",
        ),
        pytest.param(
            "gemini-cli",
            [".gemini"],
            "gemini-cli",
            ".gemini/settings.json",
            "mcpServers",
            False,
            id="gemini-cli",
        ),
        pytest.param(
            "windsurf",
            [".codeium/windsurf"],
            "windsurf",
            ".codeium/windsurf/mcp_config.json",
            "mcpServers",
            False,
            id="windsurf",
        ),
        pytest.param(
            "openclaw",
            [".openclaw/skills"],
            "openclaw",
            None,
            None,
            True,
            id="openclaw",
        ),
    ]

    @pytest.mark.parametrize(
        "detected_name,seed_dirs,applier_tool_name,mcp_file,mcp_key,supports_skills",
        _TOOL_PARAMS,
    )
    def test_not_synced_before_any_sync(
        self,
        runner,
        cli,
        tmp_path,
        monkeypatch,
        detected_name,
        seed_dirs,
        applier_tool_name,
        mcp_file,
        mcp_key,
        supports_skills,
    ):
        """Every tool shows 'not synced' when no manifest exists yet."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        for d in seed_dirs:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0, result.output
        assert "not synced" in result.output.lower(), (
            f"{detected_name} should show 'not synced' before any sync, got:\n{result.output}"
        )
        # Manifest must not exist yet
        manifest_path = tmp_path / ".apc" / "manifests" / f"{applier_tool_name}.json"
        assert not manifest_path.exists(), f"manifest should not exist before sync: {manifest_path}"

    @pytest.mark.parametrize(
        "detected_name,seed_dirs,applier_tool_name,mcp_file,mcp_key,supports_skills",
        _TOOL_PARAMS,
    )
    def test_synced_after_sync(
        self,
        runner,
        cli,
        tmp_path,
        monkeypatch,
        detected_name,
        seed_dirs,
        applier_tool_name,
        mcp_file,
        mcp_key,
        supports_skills,
    ):
        """Every tool shows 'synced' in status after apc sync runs against it.

        All tools: seed cache directly (avoids blanket collect touching real home
        dirs) then run sync — appliers are lazy so writes go to tmp_path.

        Skill-supporting tools (cursor, claude-code, openclaw) get one skill in
        the cache so the manifest records a file_path the consistency check can use.
        MCP-only tools (gemini-cli, windsurf) get one MCP server entry.
        """
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        for d in seed_dirs:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        # Seed an isolated cache — never call collect (would touch real home tool dirs)
        cache_dir = tmp_path / ".apc" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        if supports_skills:
            (cache_dir / "skills.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "test-skill",
                            "description": "A test skill",
                            "body": "Test skill body.",
                            "tags": ["test"],
                            "version": "1.0.0",
                        }
                    ]
                ),
                encoding="utf-8",
            )
        else:
            (cache_dir / "skills.json").write_text("[]", encoding="utf-8")

        (cache_dir / "mcp_servers.json").write_text(
            json.dumps(
                [
                    {
                        "name": "test-server",
                        "command": "echo",
                        "args": [],
                        "transport": "stdio",
                        "source_tool": detected_name,
                        "targets": [],
                        "env": {},
                    }
                ]
            ),
            encoding="utf-8",
        )
        (cache_dir / "memory.json").write_text("[]", encoding="utf-8")
        runner.invoke(cli, ["sync", "--tools", detected_name, "--yes", "--no-memory"])

        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0, result.output
        assert "synced" in result.output.lower(), (
            f"{detected_name} should show 'synced' after sync, got:\n{result.output}"
        )
        # Manifest must exist with last_sync_at set (keyed by applier TOOL_NAME)
        manifest_path = tmp_path / ".apc" / "manifests" / f"{applier_tool_name}.json"
        assert manifest_path.exists(), (
            f"manifest missing at {manifest_path} — "
            f"TOOL_NAME mismatch? detected={detected_name!r} applier={applier_tool_name!r}"
        )
        data = json.loads(manifest_path.read_text())
        assert data.get("last_sync_at") is not None, "last_sync_at not set in manifest"

    @pytest.mark.parametrize(
        "detected_name,seed_dirs,applier_tool_name,mcp_file,mcp_key,supports_skills",
        [p for p in _TOOL_PARAMS if p.values[5]],  # only tools that write skill files
    )
    def test_out_of_sync_when_skill_deleted(
        self,
        runner,
        cli,
        tmp_path,
        monkeypatch,
        detected_name,
        seed_dirs,
        applier_tool_name,
        mcp_file,
        mcp_key,
        supports_skills,
    ):
        """Removing a synced skill link/file causes 'out of sync' for that tool.

        Skills now live in ~/.apc/skills/ (source of truth).
        - SKILL_DIR_EXCLUSIVE tools (claude-code, openclaw): their skills dir is a
          single symlink → ~/.apc/skills/. Out-of-sync = symlink removed/broken.
        - Per-skill tools (cursor): individual link_path entries in the manifest.
          Out-of-sync = linked file deleted.
        """
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        for d in seed_dirs:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        # Seed ~/.apc/skills/test-skill/SKILL.md — the canonical source
        skills_source = tmp_path / ".apc" / "skills" / "test-skill"
        skills_source.mkdir(parents=True, exist_ok=True)
        (skills_source / "SKILL.md").write_text("# Test\nTest skill body.", encoding="utf-8")

        cache_dir = tmp_path / ".apc" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "skills.json").write_text("[]", encoding="utf-8")
        (cache_dir / "mcp_servers.json").write_text("[]", encoding="utf-8")
        (cache_dir / "memory.json").write_text("[]", encoding="utf-8")
        runner.invoke(cli, ["sync", "--tools", detected_name, "--yes", "--no-memory"])

        # Confirm synced first
        r1 = runner.invoke(cli, ["status"])
        assert "synced" in r1.output.lower(), (
            f"{detected_name}: expected synced before delete, got:\n{r1.output}"
        )

        # Break the skill link/symlink to trigger out-of-sync
        manifest_path = tmp_path / ".apc" / "manifests" / f"{applier_tool_name}.json"
        manifest_data = json.loads(manifest_path.read_text())

        if manifest_data.get("dir_sync"):
            # Exclusive-dir tool: remove the dir-level symlink
            skill_dir = Path(manifest_data["dir_sync"]["skill_dir"])
            skill_dir.unlink()
        else:
            # Per-skill tool: delete a linked skill file
            link_paths = [
                v["link_path"]
                for v in manifest_data.get("linked_skills", {}).values()
                if "link_path" in v
            ]
            assert link_paths, f"no link_paths in manifest for {detected_name}"
            Path(link_paths[0]).unlink()

        r2 = runner.invoke(cli, ["status"])
        assert "out of sync" in r2.output.lower(), (
            f"{detected_name}: expected 'out of sync' after delete, got:\n{r2.output}"
        )


# ---------------------------------------------------------------------------
# Phase 3: apc collect
# ---------------------------------------------------------------------------


class TestCollect:
    def test_collect_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["collect", "--yes"])
        assert result.exit_code == 0, result.output
        cache_dir = HOME / ".apc" / "cache"
        assert cache_dir.is_dir()
        assert (cache_dir / "skills.json").exists()
        assert (cache_dir / "mcp_servers.json").exists()
        assert (cache_dir / "memory.json").exists()

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
        expected = {"claude-code", "cursor", "gemini-cli", "github-copilot", "windsurf"}
        assert expected.issubset(sources), f"Missing sources: {expected - sources}"

    def test_memory_has_claude_entry(self, runner, cli):
        runner.invoke(cli, ["collect", "--yes"])
        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        sources = {e.get("source_tool") for e in data}
        assert "claude-code" in sources

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
        assert (HOME / ".apc" / "cache" / "skills.json").exists()

    def test_skill_list_shows_test_skill(self, runner, cli):
        result = runner.invoke(cli, ["skill", "list"])
        assert "test-skill" in result.output
        data = json.loads((HOME / ".apc" / "cache" / "skills.json").read_text())
        names = [s["name"] for s in data]
        assert "test-skill" in names

    def test_skill_list_shows_oc_skill(self, runner, cli):
        result = runner.invoke(cli, ["skill", "list"])
        assert "oc-skill" in result.output
        data = json.loads((HOME / ".apc" / "cache" / "skills.json").read_text())
        names = [s["name"] for s in data]
        assert "oc-skill" in names

    def test_skill_show_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["skill", "show"])
        assert result.exit_code == 0, result.output
        assert (HOME / ".apc" / "cache" / "skills.json").exists()

    def test_skill_show_by_name(self, runner, cli):
        result = runner.invoke(cli, ["skill", "show", "test-skill"])
        assert result.exit_code == 0
        assert "test skill" in result.output.lower() or "test-skill" in result.output.lower()
        # Skill must be in cache to be displayed
        data = json.loads((HOME / ".apc" / "cache" / "skills.json").read_text())
        assert any(s["name"] == "test-skill" for s in data)


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
        assert (HOME / ".apc" / "cache" / "memory.json").exists()

    def test_memory_add_exits_zero(self, runner, cli):
        result = runner.invoke(
            cli, ["memory", "add", "Docker test pref", "--category", "preference"]
        )
        assert result.exit_code == 0, result.output
        assert (HOME / ".apc" / "cache" / "memory.json").exists()

    def test_memory_add_persists(self, runner, cli):
        runner.invoke(cli, ["memory", "add", "Docker test pref", "--category", "preference"])
        result = runner.invoke(cli, ["memory", "list"])
        assert "Docker test pref" in result.output
        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        contents = " ".join(e.get("content", "") + e.get("body", "") for e in data)
        assert "Docker test pref" in contents

    def test_memory_add_writes_to_cache(self, runner, cli):
        runner.invoke(cli, ["memory", "add", "Unique docker mem", "--category", "workflow"])
        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        contents = [e.get("content", "") for e in data]
        assert "Unique docker mem" in contents

    def test_memory_show_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["memory", "show"])
        assert result.exit_code == 0, result.output
        assert (HOME / ".apc" / "cache" / "memory.json").exists()

    def test_memory_list_shows_collected_files(self, runner, cli):
        result = runner.invoke(cli, ["memory", "list"])
        assert "claude" in result.output.lower() or "openclaw" in result.output.lower()
        data = json.loads((HOME / ".apc" / "cache" / "memory.json").read_text())
        assert len(data) > 0, "memory.json is empty after collect"


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
        assert (HOME / ".apc" / "cache" / "mcp_servers.json").exists()

    def test_mcp_list_shows_servers(self, runner, cli):
        result = runner.invoke(cli, ["mcp", "list"])
        assert "test-claude-mcp" in result.output
        data = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        names = [s["name"] for s in data]
        assert "test-claude-mcp" in names

    def test_mcp_remove_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["mcp", "remove", "test-claude-mcp", "-y"])
        assert result.exit_code == 0, result.output
        data = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        names = [s["name"] for s in data]
        assert "test-claude-mcp" not in names

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
        assert "test-cursor-mcp" in result.output
        data = json.loads((HOME / ".apc" / "cache" / "mcp_servers.json").read_text())
        names = [s["name"] for s in data]
        assert "test-claude-mcp" not in names
        assert "test-cursor-mcp" in names


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
        assert (HOME / ".claude.json").exists()
        data = json.loads((HOME / ".claude.json").read_text())
        assert "mcpServers" in data

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
        assert (HOME / ".cursor" / "mcp.json").exists()
        data = json.loads((HOME / ".cursor" / "mcp.json").read_text())
        assert "mcpServers" in data
        assert len(data["mcpServers"]) > 0
        rules_dir = HOME / ".cursor" / "rules"
        assert rules_dir.is_dir()
        assert len(list(rules_dir.glob("*.mdc"))) > 0, "No .mdc skill files written to cursor"

    def test_sync_writes_cursor_mcp(self, runner, cli):
        runner.invoke(cli, ["sync", "--tools", "cursor", "--yes", "--no-memory", "--override-mcp"])
        data = json.loads((HOME / ".cursor" / "mcp.json").read_text())
        assert "mcpServers" in data
        assert len(data["mcpServers"]) > 0

    def test_sync_dry_run(self, runner, cli):
        claude_before = (HOME / ".claude.json").read_text()
        result = runner.invoke(cli, ["sync", "--dry-run", "--all", "--yes"])
        assert result.exit_code == 0
        assert "no files written" in result.output.lower()
        assert (HOME / ".claude.json").read_text() == claude_before, "dry-run modified .claude.json"

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
        data = json.loads((HOME / ".claude.json").read_text())
        assert "mcpServers" in data
        assert len(data["mcpServers"]) > 0

    def test_mcp_sync_writes_servers(self, runner, cli):
        runner.invoke(cli, ["mcp", "sync", "--tools", "claude-code", "--yes"])
        data = json.loads((HOME / ".claude.json").read_text())
        assert "mcpServers" in data
        assert len(data["mcpServers"]) > 0

    def test_skill_sync_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["skill", "sync", "--tools", "claude-code", "--yes"])
        assert result.exit_code == 0, result.output
        commands_dir = HOME / ".claude" / "commands"
        assert commands_dir.is_dir()
        assert len(list(commands_dir.glob("*.md"))) > 0, "No skill files written to claude commands"

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
        assert (HOME / ".apc").is_dir()

    def test_models_list_exits_zero(self, runner, cli):
        result = runner.invoke(cli, ["model", "list"])
        assert result.exit_code == 0, result.output
        assert (HOME / ".apc").is_dir()

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
        auth_path = HOME / ".apc" / "auth-profiles.json"
        assert auth_path.exists(), "auth-profiles.json not written by configure"
        data = json.loads(auth_path.read_text())
        assert any("anthropic" in k for k in data.get("profiles", {}))

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


# ---------------------------------------------------------------------------
# Phase 11: apc install (real GitHub network calls, no mocks)
# ---------------------------------------------------------------------------


class TestInstall:
    """Real-command tests for apc install.

    Uses anthropics/skills as the test repo — a stable public repo with known skills.
    All commands invoke the real GitHub API and write real files.
    """

    TEST_REPO = "anthropics/skills"
    KNOWN_SKILL = "pdf"  # small, stable skill

    def test_install_invalid_repo_url(self, runner, cli):
        """Full GitHub URLs are rejected — must be owner/repo slug."""
        result = runner.invoke(cli, ["install", "https://github.com/anthropics/skills"])
        assert result.exit_code != 0
        assert "owner/repo format" in result.output.lower()

    def test_install_invalid_no_slash(self, runner, cli):
        """A bare name with no slash is rejected immediately."""
        result = runner.invoke(cli, ["install", "notaslug"])
        assert result.exit_code != 0

    def test_install_list_real_repo(self, runner, cli):
        """--list fetches and prints the real skill index from GitHub."""
        result = runner.invoke(cli, ["install", self.TEST_REPO, "--list"])
        assert result.exit_code == 0
        assert "•" in result.output
        assert "skill(s) found" in result.output
        assert self.KNOWN_SKILL in result.output
        # --list is read-only: nothing written to ~/.apc/skills/
        skills_dir = Path.home() / ".apc" / "skills"
        if skills_dir.exists():
            assert self.KNOWN_SKILL not in [d.name for d in skills_dir.iterdir()]

    def test_install_single_skill(self, runner, cli, tmp_path, monkeypatch):
        """Install one real skill — verifies cache entry and SKILL.md on disk."""
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(
            cli,
            ["install", self.TEST_REPO, "--skill", self.KNOWN_SKILL, "-t", "cursor", "-y"],
        )
        assert result.exit_code == 0, result.output
        assert "✓" in result.output
        skill_file = tmp_path / ".apc" / "skills" / self.KNOWN_SKILL / "SKILL.md"
        assert skill_file.exists(), "SKILL.md not written to ~/.apc/skills/"
        assert len(skill_file.read_text()) > 0

    def test_install_multiple_skills(self, runner, cli, tmp_path, monkeypatch):
        """Install two real skills in one command."""
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(
            cli,
            [
                "install",
                self.TEST_REPO,
                "--skill",
                "pdf",
                "--skill",
                "skill-creator",
                "-t",
                "cursor",
                "-y",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Installed 2 skill(s)" in result.output
        assert (tmp_path / ".apc" / "skills" / "pdf" / "SKILL.md").exists()
        assert (tmp_path / ".apc" / "skills" / "skill-creator" / "SKILL.md").exists()

    def test_install_nonexistent_skill(self, runner, cli, tmp_path, monkeypatch):
        """A skill name that does not exist in the repo prints a clear message."""
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(
            cli,
            [
                "install",
                self.TEST_REPO,
                "--skill",
                "totally-nonexistent-xyz",
                "-t",
                "cursor",
                "-y",
            ],
        )
        assert result.exit_code == 0  # not a crash — graceful message
        assert (
            "not found" in result.output.lower()
            or "no skills were installed" in result.output.lower()
        )

    def test_install_all(self, runner, cli, tmp_path, monkeypatch):
        """--all installs every skill from the repo."""
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(cli, ["install", self.TEST_REPO, "--all", "-t", "cursor", "-y"])
        assert result.exit_code == 0, result.output
        assert "✓" in result.output
        skills_dir = tmp_path / ".apc" / "skills"
        installed = list(skills_dir.iterdir())
        assert len(installed) > 5, f"Expected >5 skills installed, got {len(installed)}"

    def test_install_yes_skips_confirmation(self, runner, cli, tmp_path, monkeypatch):
        """-y completes without showing a Proceed? prompt."""
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(
            cli,
            ["install", self.TEST_REPO, "--skill", self.KNOWN_SKILL, "-t", "cursor", "-y"],
        )
        assert result.exit_code == 0
        assert "Proceed?" not in result.output
        skill_md = tmp_path / ".apc" / "skills" / self.KNOWN_SKILL / "SKILL.md"
        assert skill_md.exists(), "SKILL.md not written even with -y"
        assert len(skill_md.read_text()) > 0

    def test_install_target_all_agents(self, runner, cli, tmp_path, monkeypatch):
        """--target '*' installs to all detected tools."""
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".cursor").mkdir()
        result = runner.invoke(
            cli,
            ["install", self.TEST_REPO, "--skill", self.KNOWN_SKILL, "--target", "*", "-y"],
        )
        assert result.exit_code == 0, result.output
        assert "✓" in result.output
        skill_md = tmp_path / ".apc" / "skills" / self.KNOWN_SKILL / "SKILL.md"
        assert skill_md.exists(), "SKILL.md not written when targeting all agents"


# ---------------------------------------------------------------------------
# Phase 12: install → sync end-to-end flow (no mocks)
# ---------------------------------------------------------------------------


class TestInstallThenSync:
    """Real end-to-end install → sync flow.

    Installs real skills from GitHub, runs apc sync, and verifies the
    resulting file-system state in the target tool's directory.
    """

    TEST_REPO = "anthropics/skills"
    KNOWN_SKILL = "pdf"

    def test_install_then_sync_symlinks_skill_to_tool(self, runner, cli, tmp_path, monkeypatch):
        """Skill installed via apc install is symlinked into tool dir after apc sync."""
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".cursor" / "mcp.json").write_text("{}")

        r1 = runner.invoke(
            cli, ["install", self.TEST_REPO, "--skill", self.KNOWN_SKILL, "-t", "cursor", "-y"]
        )
        assert r1.exit_code == 0, r1.output

        r2 = runner.invoke(cli, ["sync", "--tools", "cursor", "--yes"])
        assert r2.exit_code == 0, r2.output

        cursor_skill = tmp_path / ".cursor" / "rules" / f"{self.KNOWN_SKILL}.mdc"
        assert cursor_skill.exists(), f"Skill not found at {cursor_skill} after sync"

    def test_installed_skill_appears_in_skill_list(self, runner, cli, tmp_path, monkeypatch):
        """Installed skill appears in apc skill list immediately after install."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner.invoke(
            cli, ["install", self.TEST_REPO, "--skill", self.KNOWN_SKILL, "-t", "cursor", "-y"]
        )

        result = runner.invoke(cli, ["skill", "list"])
        assert result.exit_code == 0
        assert self.KNOWN_SKILL in result.output
        skill_md = tmp_path / ".apc" / "skills" / self.KNOWN_SKILL / "SKILL.md"
        assert skill_md.exists(), "SKILL.md missing after install"
        assert len(skill_md.read_text()) > 0

    def test_install_multiple_then_sync_all_land_in_tool(self, runner, cli, tmp_path, monkeypatch):
        """All installed skills land in the tool directory after sync."""
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".cursor" / "mcp.json").write_text("{}")

        skills = ["pdf", "skill-creator"]
        r_install = runner.invoke(
            cli,
            [
                "install",
                self.TEST_REPO,
                "--skill",
                skills[0],
                "--skill",
                skills[1],
                "-t",
                "cursor",
                "-y",
            ],
        )
        assert r_install.exit_code == 0, r_install.output
        assert "Installed 2 skill(s)" in r_install.output

        r_sync = runner.invoke(cli, ["sync", "--tools", "cursor", "--yes"])
        assert r_sync.exit_code == 0, r_sync.output

        rules_dir = tmp_path / ".cursor" / "rules"
        for name in skills:
            assert (rules_dir / f"{name}.mdc").exists(), (
                f"Skill {name} missing from cursor after sync"
            )

    def test_install_all_then_sync_dry_run(self, runner, cli, tmp_path, monkeypatch):
        """Install all skills then dry-run sync — no files written but plan is shown."""
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".cursor" / "mcp.json").write_text("{}")

        r_install = runner.invoke(cli, ["install", self.TEST_REPO, "--all", "-t", "cursor", "-y"])
        assert r_install.exit_code == 0, r_install.output

        skills_dir = tmp_path / ".apc" / "skills"
        installed_count = len(list(skills_dir.iterdir())) if skills_dir.exists() else 0
        assert installed_count > 5, (
            f"Expected >5 skills installed, got {installed_count}. "
            f"Install output:\n{r_install.output}"
        )

        r_sync = runner.invoke(cli, ["sync", "--tools", "cursor", "--dry-run"])
        assert r_sync.exit_code == 0
        assert "No files written" in r_sync.output or "dry-run" in r_sync.output.lower()

    def test_status_synced_after_install_and_sync(self, runner, cli, tmp_path, monkeypatch):
        """apc status shows cursor as synced after a full install + sync cycle."""
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".cursor" / "mcp.json").write_text("{}")

        runner.invoke(
            cli, ["install", self.TEST_REPO, "--skill", self.KNOWN_SKILL, "-t", "cursor", "-y"]
        )
        runner.invoke(cli, ["sync", "--tools", "cursor", "--yes"])

        r_status = runner.invoke(cli, ["status"])
        assert r_status.exit_code == 0
        assert "synced" in r_status.output.lower()


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
        assert (export_path / "apc-export.json").exists(), "apc-export.json not created"
        assert (export_path / "cache").is_dir(), "cache/ dir not created"
        assert (export_path / "cache" / "skills.json").exists()
        assert (export_path / "cache" / "mcp_servers.json").exists()

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
        assert (HOME / ".apc" / "cache" / "skills.json").exists()
        assert (HOME / ".apc" / "cache" / "mcp_servers.json").exists()

    def test_import_invalid_path(self, runner, cli, tmp_path):
        result = runner.invoke(cli, ["import", str(tmp_path / "nonexistent"), "--yes"])
        assert result.exit_code != 0

    def test_import_suggests_sync(self, runner, cli, export_path):
        self._do_export(runner, cli, export_path)
        result = runner.invoke(cli, ["import", str(export_path), "--yes"])
        assert "apc sync" in result.output
        assert (HOME / ".apc" / "cache" / "skills.json").exists()

    def test_import_no_secrets_flag(self, runner, cli, export_path):
        self._do_export(runner, cli, export_path)
        result = runner.invoke(cli, ["import", str(export_path), "--no-secrets", "--yes"])
        assert result.exit_code == 0, result.output
        assert (HOME / ".apc" / "cache" / "skills.json").exists()
        assert (HOME / ".apc" / "cache" / "mcp_servers.json").exists()


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
