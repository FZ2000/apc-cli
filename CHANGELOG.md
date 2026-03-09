# Changelog

## [0.1.2] - 2026-03-09

### Added
- `apc collect --dry-run` — preview what would be collected without writing to cache (#25)
- `apc sync --dry-run` enhanced to show exact file paths per tool (#24)
- `apc memory list` rewritten as Rich tables with `--tool` filter (#21)
- `apc memory remove` command — remove by ID prefix, by tool, or clear all (#48)
- `apc skill remove` and `apc unsync` commands for full lifecycle management (#71)
- Windsurf and GitHub Copilot native sync support (#71)
- Gemini CLI skill directory symlink support (#71)

### Fixed
- Skills now propagate to all synced tools unconditionally after `apc install` (#71)
- `--target`/`-t` removed from `apc install` (skills always land in `~/.apc/skills/`) (#71)


## v0.1.0 — Initial Release

- Extract configs from Claude, Cursor, Gemini, Copilot, Windsurf, and OpenClaw
- Sync skills, MCP servers, and memory to target tools
- Marketplace support for installing skills from GitHub repos
- LLM provider configuration with multi-provider auth profiles
- Memory management with add/list/show/sync commands
- MCP server config management
- Rich terminal UI with paged output
