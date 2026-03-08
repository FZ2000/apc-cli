---
title: "How to Sync Your AI Memory Across Claude Code, Cursor, Copilot, and More"
published: true
tags: ai, devtools, python, productivity
description: Stop re-configuring every AI coding tool from scratch. apc-cli syncs your skills, memory, and MCP servers across all your tools with one command.
canonical_url: https://dev.to/fz2000/how-to-sync-your-ai-memory-across-claude-code-cursor-copilot-and-more
---

# How to Sync Your AI Memory Across Claude Code, Cursor, Copilot, and More

If you use more than one AI coding assistant, you've hit this wall.

You spend time training Claude Code on your codebase — your naming conventions, your architecture decisions, your preferred libraries. Then you open Cursor for a specific task, and it knows nothing. Back to square one. Every tool is an island.

It gets worse when you set up a new machine. All that context, gone. Or when you add a new AI tool to your workflow and have to bootstrap it manually from memory.

**This is the problem `apc-cli` solves.**

## What apc-cli does

`apc-cli` is a local CLI that treats your AI context — skills, memory entries, and MCP server configs — as a first-class asset you own and can move around.

Three commands cover the core workflow:

```bash
apc collect   # pull configs out of every installed AI tool
apc status    # see what's synced and what isn't
apc sync      # push everything to all your tools
```

After running those, Claude Code, Cursor, Gemini CLI, Copilot, and Windsurf all share the same context. Change something in one tool, run `apc collect && apc sync`, and everything stays current.

## Install

```bash
pip install apc-cli
```

Or via the one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/FZ2000/apc-cli/main/install.sh | bash
```

## Walkthrough

### 1. See what tools you have and what state they're in

```bash
$ apc status

Status
──────────

          Detected Tools
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Tool           ┃    Status     ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ claude-code    │   ● synced    │
│ cursor         │ ⚠ out of sync │
│ gemini-cli     │ ○ not synced  │
│ github-copilot │ ○ not synced  │
│ openclaw       │   ● synced    │
│ windsurf       │   ● synced    │
└────────────────┴───────────────┘

      Local Cache
┏━━━━━━━━━━━━━┳━━━━━━━┓
┃ Category    ┃ Count ┃
┡━━━━━━━━━━━━━╇━━━━━━━┩
│ Skills      │    21 │
│ MCP Servers │     6 │
│ Memory      │   203 │
└─────────────┴───────┘
```

Three tools out of sync. `apc sync` fixes that.

### 2. Collect what each tool currently knows

```bash
apc collect
```

This scans every installed tool and pulls their skills, memory files, and MCP server configs into a local cache at `~/.apc/`. Nothing is written back yet — collect is read-only.

### 3. Sync to all your tools

```bash
apc sync
```

Or target specific tools:

```bash
apc sync --tools cursor,gemini-cli
```

### 4. Preview before writing

```bash
apc sync --dry-run
```

Shows exactly what would change, without touching any files.

---

## Memory sync across tools

Each AI tool stores memory differently. Claude Code uses `CLAUDE.md`. Cursor uses `.cursorrules`. Gemini CLI and Windsurf have their own formats.

apc-cli handles the translation. When you run `apc memory sync`, it uses an LLM (your choice — Anthropic, OpenAI, Gemini, or any local model via Ollama) to rewrite your memory entries into whatever format the target tool expects.

```bash
# Add a memory entry once — sync everywhere
apc memory add "Always use TypeScript strict mode in this project"
apc memory sync
```

The LLM never sees your API keys or secrets. Those are stripped at collection time and stored in the OS keychain.

### Configure your LLM provider

```bash
apc configure
```

Supports: Anthropic, OpenAI, Gemini, Qwen, local models via Ollama or LM Studio.

---

## MCP server sync

If you use [Model Context Protocol](https://modelcontextprotocol.io/) servers with Claude Code or Cursor, you've probably configured the same server in multiple places. apc-cli treats your MCP config as a single source of truth.

```bash
apc collect       # picks up MCP configs from all tools
apc mcp list      # see what's in the cache
apc mcp sync      # push to all your tools
```

API keys in MCP server configs are automatically detected, redacted from the JSON, and stored in the OS keychain. The config files stay secret-free.

---

## New machine setup

The export/import workflow makes machine migrations straightforward:

```bash
# On your old machine
apc export ~/apc-backup

# On your new machine
apc import ~/apc-backup
```

Secrets are encrypted with [age](https://age-encryption.org/) before export. Transfer `~/.apc/age-identity.txt` once via a secure channel (1Password, etc.), and everything else can go through a private git repo or cloud storage safely.

---

## Install skills from GitHub

apc-cli has a skill registry concept — shareable instruction snippets that live in GitHub repos and can be installed directly into your AI tools.

```bash
# Browse skills in a repo
apc install owner/repo --list

# Install a specific skill
apc install owner/repo --skill my-skill

# Install to specific tools only
apc install owner/repo --skill my-skill --target claude-code,cursor
```

---

## Why no cloud?

Every other sync tool for AI contexts wants a cloud account, a subscription, and your data on their servers. apc-cli is entirely local. Your memory stays on your machine. Your API keys go to your OS keychain, not a config file. No account required, no telemetry, MIT licensed.

---

## What's next

Currently supported: **Claude Code, Cursor, Gemini CLI, GitHub Copilot, Windsurf, OpenClaw**.

Contributions welcome — especially if you use a tool that isn't on the list yet.

- GitHub: [https://github.com/FZ2000/apc-cli](https://github.com/FZ2000/apc-cli)
- PyPI: [https://pypi.org/project/apc-cli/](https://pypi.org/project/apc-cli/)

```bash
pip install apc-cli
apc collect && apc status
```
