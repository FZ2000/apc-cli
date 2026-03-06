# APC — AI Personal Context Manager

**Collect, unify, and sync AI tool configurations across Claude Code, Cursor, Gemini CLI, GitHub Copilot, Windsurf, and OpenClaw.**

[![CI](https://github.com/FZ2000/apc-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/FZ2000/apc-cli/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/FZ2000/apc-cli?style=social)](https://github.com/FZ2000/apc-cli)

---

## Why APC?

You use multiple AI coding tools. Each one stores skills, MCP server configs, and memory in its own format, in its own directory. When you switch tools or set up a new machine, you lose everything — or spend hours copying files around.

**APC fixes this.** It extracts your configs from every installed tool into a single local cache, then syncs them back out to any combination of targets. Skills, MCP servers, memory, API keys — all managed from one CLI. No cloud account required.

## At a Glance

```
$ apc status

  ╭─ Detected Tools ────────────────────╮
  │  claude-code      synced            │
  │  cursor           synced            │
  │  gemini-cli       not synced        │
  │  github-copilot   synced            │
  ╰─────────────────────────────────────╯

  ╭─ Local Cache ───────────────────────╮
  │  Skills        12                   │
  │  MCP Servers    4                   │
  │  Memory         7                   │
  ╰─────────────────────────────────────╯

  LLM: anthropic/claude-sonnet-4-6 (1 auth profile(s))
```

## Features

- **Multi-tool sync** — extract and apply skills, MCP servers, and memory across 6 supported AI tools
- **MCP server management** — sync Model Context Protocol server configs between tools with secret redaction and OS keychain storage
- **Skill installation** — install reusable instruction snippets directly from GitHub repositories
- **LLM-powered memory sync** — transform and merge memory entries across tools using any configured LLM provider
- **Offline-first** — no cloud account or login required; everything runs locally
- **Smart conflict resolution** — detects overlapping configs from multiple tools and lets you choose
- **Manifest tracking** — tracks what APC wrote vs. what you changed, so user edits are never overwritten

## Supported Tools

Claude Code, Cursor, Gemini CLI, GitHub Copilot, Windsurf, and OpenClaw.

## Installation

### pip (recommended)

```bash
pip install git+https://github.com/FZ2000/apc-cli.git
```

### One-liner

```bash
curl -fsSL https://raw.githubusercontent.com/FZ2000/apc-cli/main/install.sh | bash
```

This clones the repo to `~/.apc-cli`, creates a venv, and symlinks `apc` into `~/.local/bin`.

## Quick Start

```bash
# 1. Extract configs from all installed AI tools into the local cache
apc collect

# 2. See what was collected
apc status

# 3. Sync everything to all your tools
apc sync

# 4. Or sync to specific tools only
apc sync --tools cursor,gemini-cli

# 5. Install skills from a GitHub repo
apc install owner/repo --skill my-skill

# 6. Add a memory entry manually
apc memory add "Always use TypeScript strict mode"

# 7. Set up an LLM provider for memory sync
apc configure
```

## Command Reference

### Core Workflow

| Command | Description |
|---------|-------------|
| `apc collect` | Extract skills, MCP servers, and memory from installed AI tools |
| `apc status` | Show detected tools and local cache summary |
| `apc sync` | Sync all cached configs to target tools |

**Options for `collect`:**

| Flag | Description |
|------|-------------|
| `--tools <list>` | Comma-separated tool list (e.g., `claude-code,cursor`) |
| `--no-memory` | Skip collecting memory entries |
| `--yes`, `-y` | Skip confirmation prompts |

**Options for `sync`:**

| Flag | Description |
|------|-------------|
| `--tools <list>` | Comma-separated tool list (e.g., `cursor,gemini-cli`) |
| `--all` | Apply to all detected tools without prompting |
| `--no-memory` | Skip memory entries |
| `--override-mcp` | Replace existing MCP servers instead of merging |
| `--dry-run` | Show what would be applied without writing |
| `--yes`, `-y` | Skip confirmation prompts |

### Skills

| Command | Description |
|---------|-------------|
| `apc skill list` | List all skills in the cache |
| `apc skill show [name]` | View full skill details with pagination |
| `apc skill sync` | Sync skills to target tools |

### Install

| Command | Description |
|---------|-------------|
| `apc install <repo>` | Install skills from a GitHub repository |
| `apc install <repo> --list` | List available skills in the repo |
| `apc install <repo> --skill <name>` | Install a specific skill |
| `apc install <repo> --all` | Install all skills from the repo |

**Options:**

| Flag | Description |
|------|-------------|
| `--skill`, `-s` | Skill name(s) to install (repeatable, or `'*'` for all) |
| `--target`, `-t` | Target tool(s) to install to (repeatable, or `'*'` for all detected) |
| `--branch` | Git branch to fetch from (default: `main`) |
| `--list` | List available skills without installing |
| `--yes`, `-y` | Skip confirmation prompts |

### Memory

| Command | Description |
|---------|-------------|
| `apc memory list` | List all memory entries |
| `apc memory show` | View full memory details with pagination |
| `apc memory add "<text>"` | Add a memory entry manually |
| `apc memory sync` | Sync memory to target tools via LLM |

### MCP Servers

| Command | Description |
|---------|-------------|
| `apc mcp list` | List cached MCP server configs |
| `apc mcp sync` | Sync MCP servers to target tools |
| `apc mcp remove <name>` | Remove an MCP server from the cache |

### Export / Import

| Command | Description |
|---------|-------------|
| `apc export [path]` | Export configs to a portable directory with age-encrypted secrets |
| `apc import [path]` | Import configs from an export directory, decrypting secrets |

**Options:**

| Flag | Description |
|------|-------------|
| `--no-secrets` | Skip secret encryption/decryption |
| `--yes`, `-y` | Skip confirmation prompts |

**Workflow:** export on machine A, commit the directory to a private repo, pull on machine B, import. Transfer `~/.apc/age-identity.txt` (private key) to the target machine once via a secure channel. Secrets stay safe even if the repo becomes public.

### LLM Configuration

| Command | Description |
|---------|-------------|
| `apc configure` | Interactive LLM provider setup wizard |
| `apc model status` | Show default model and auth profiles |
| `apc model list` | List configured providers and models |
| `apc model set <provider/model>` | Set the default model |
| `apc model auth add` | Add an auth profile |
| `apc model auth remove <key>` | Remove an auth profile |

## How It Works

```
┌──────────────┐     collect     ┌──────────────┐      sync      ┌──────────────┐
│  Claude Code │─────────────┐   │              │   ┌────────────│  Claude Code │
│  Cursor      │─────────────┤   │  Local Cache │   ├────────────│  Cursor      │
│  Gemini CLI  │─────────────┤──▶│  (~/.apc/)   │──▶├────────────│  Gemini CLI  │
│  Copilot     │─────────────┤   │              │   ├────────────│  Copilot     │
│  Windsurf    │─────────────┤   │              │   ├────────────│  Windsurf    │
│  OpenClaw    │─────────────┘   └──────────────┘   └────────────│  OpenClaw    │
└──────────────┘                                                 └──────────────┘
     Extract                     Skills + MCP +                       Apply
                                 Memory + Secrets
```

**Data flow:**

1. **Extract** — `apc collect` scans installed tools, pulls out skills, MCP server configs, and memory files
2. **Cache** — everything is stored in `~/.apc/` as JSON; secrets are redacted and stored in the OS keychain
3. **Sync** — `apc sync` writes configs to target tools in their native formats, using manifests to track changes

### Directory Structure

```
~/.apc/
├── cache/
│   ├── skills.json          # Collected skills from all tools
│   ├── mcp_servers.json     # Collected MCP server configs
│   └── memory.json          # Collected memory entries
├── skills/                  # Installed skills (source of truth)
│   └── <skill-name>/
│       └── SKILL.md
├── manifests/               # Per-tool sync tracking
├── auth-profiles.json       # LLM API credentials
├── models.json              # Model preferences
└── age-identity.txt         # Age private key (export/import encryption)
```

## Configuration

### LLM Providers

Memory sync uses an LLM to transform entries into each tool's native format. APC supports multiple providers:

**Interactive setup:**

```bash
apc configure
```

**Non-interactive setup:**

```bash
# Anthropic
apc configure --provider anthropic --api-key "$ANTHROPIC_API_KEY"

# OpenAI
apc configure --provider openai --api-key "$OPENAI_API_KEY"

# Google Gemini
apc configure --provider gemini --api-key "$GEMINI_API_KEY"

# Custom / local (Ollama, vLLM, LM Studio)
apc configure --provider custom --base-url "http://localhost:11434/v1" \
  --model-id "llama-3"
```

**Supported LLM providers:** Anthropic, OpenAI, Google Gemini, Qwen (Alibaba), GLM (Zhipu), MiniMax, Kimi (Moonshot), and any OpenAI-compatible or Anthropic-compatible endpoint.

## Development

```bash
# Clone and install
git clone https://github.com/FZ2000/apc-cli.git
cd apc-cli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest -v

# Lint and format
ruff check src/ tests/
ruff format --check src/ tests/

# Run integration tests in Docker
docker build -t apc-test -f tests/Dockerfile .
docker run --rm apc-test
```

## Contributing

Contributions are welcome. Please open an issue to discuss your idea before submitting a PR.

- Follow the existing code style (`ruff` for linting and formatting)
- Add tests for new functionality
- Keep commits focused and atomic

## License

[MIT](LICENSE)
