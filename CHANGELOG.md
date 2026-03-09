# Changelog

## [0.1.2] - 2026-03-09

### Added
- `apc collect --dry-run` — preview what would be collected without writing to cache (#25)
- `apc sync --dry-run` enhanced to show exact file paths per tool (#24)
- Shell completion setup for bash, zsh, and fish documented (#23)

### Fixed
- Input validation on `apc install`: repo/branch allowlisted, skill names sanitized on import, no redirect following (#27, #28, #30)
- MCP config files now written with chmod 600; secrets scrubbed from `apc export` archives (#32, #35)
- LLM memory write guard narrowed; paths with `~/` now correctly resolved; Copilot paths made absolute (#37, #38–#43, #42)
- Memory deduplication uses stable content-hash key; `apc memory add` entries use new schema (#36, #45)
- `~/.apc/skills/` directory always created after `apc install` even if no skills are fetched
- CLI `--version` now reads from `importlib.metadata` instead of a hardcoded string

### Docs
- README: `apc --version`, shell completion setup, CLI basics section (#23, #26)


## v0.1.0 — Initial Release

- Extract configs from Claude, Cursor, Gemini, Copilot, Windsurf, and OpenClaw
- Sync skills, MCP servers, and memory to target tools
- Marketplace support for installing skills from GitHub repos
- LLM provider configuration with multi-provider auth profiles
- Memory management with add/list/show/sync commands
- MCP server config management
- Rich terminal UI with paged output
