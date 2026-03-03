# apc — AI Personal Context

[![CI](https://github.com/FZ2000/apc-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/FZ2000/apc-cli/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Collect, manage, and sync AI agent configs (skills, MCP servers, memory, settings) across tools and machines.

## Features

- **Collect** — extract configs from installed AI tools into a local cache
- **Sync** — apply cached configs to any combination of target tools
- **Skills** — manage reusable instruction snippets across tools
- **Memory** — persistent context entries shared across AI agents
- **MCP Servers** — sync Model Context Protocol server configs
- **Marketplace** — install skills from GitHub repositories or local directories
- **LLM Config** — configure API keys and model preferences for multiple providers

## Supported Tools

| Tool | Extract | Apply |
|------|---------|-------|
| Claude | ✅ | ✅ |
| Cursor | ✅ | ✅ |
| Gemini | ✅ | ✅ |
| GitHub Copilot | ✅ | ✅ |
| Windsurf | ✅ | ✅ |
| OpenClaw | ✅ | ✅ |

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# Extract configs from installed AI tools
apc collect

# See what's in your local cache
apc status

# Sync configs to target tools
apc sync

# Sync to specific tools only
apc sync --tools cursor,gemini

# Install a skill from a marketplace
apc install owner/repo/skill-name

# Manage memory entries
apc memory show
apc memory add my-note.md
```

## Commands

| Command | Description |
|---------|-------------|
| `apc collect` | Extract configs from installed AI tools |
| `apc status` | Show local cache contents |
| `apc sync` | Sync cache to target tools |
| `apc skill show` | View skill details |
| `apc skill list` | List available skills |
| `apc memory show` | View memory entries |
| `apc memory add` | Add a memory entry |
| `apc memory list` | List memory entries |
| `apc install` | Install a skill from a marketplace |
| `apc marketplace add` | Add a marketplace source |
| `apc marketplace list` | List configured marketplaces |
| `apc mcp` | Manage MCP server configs |
| `apc configure` | Set up LLM API keys and auth |
| `apc models` | Configure model preferences |

## Configuration

APC stores its data in `~/.apc/`:

```
~/.apc/
  cache.json          # Local cache of collected configs
  marketplaces.json   # Configured marketplace sources
  auth-profiles.json  # LLM API credentials
  models.json         # Model preferences
  skills/             # Installed skill files
```

## Development

```bash
# Clone and install with dev dependencies
git clone https://github.com/FZ2000/apc-cli.git
cd apc-cli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest -v

# Lint and format check
ruff check src/ tests/
ruff format --check src/ tests/
```

## License

[MIT](LICENSE)
