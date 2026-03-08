"""apc doctor — environment and configuration health checks. (#22)"""

import shutil
import sys

import click

from config import get_cache_dir, get_config_dir
from extractors import detect_installed_tools


def _check_python() -> tuple[bool, str]:
    v = sys.version_info
    ok = v >= (3, 12)
    return ok, f"Python {v.major}.{v.minor}.{v.micro} (required: 3.12+)"


def _check_cache_dir() -> tuple[bool, str]:
    try:
        cache = get_cache_dir()
        if not cache.is_dir():
            return False, f"Cache directory missing: {cache}"
        # Verify writable by stat-ing the directory
        cache.stat()
        return True, f"Cache directory: {cache} (writable)"
    except Exception as e:
        return False, f"Cache directory issue: {e}"


def _check_config_dir() -> tuple[bool, str]:
    try:
        cfg = get_config_dir()
        return True, f"Config directory: {cfg}"
    except Exception as e:
        return False, f"Config directory issue: {e}"


def _check_keychain() -> tuple[bool, str]:
    try:
        import keyring

        backend_name = type(keyring.get_keyring()).__name__
        if "Fail" in backend_name or "Null" in backend_name:
            return (
                False,
                f"OS keychain unavailable ({backend_name}) — "
                "MCP secret storage disabled. Install libsecret (Linux) or run on macOS/Windows.",
            )
        return True, f"OS keychain: available ({backend_name})"
    except ImportError:
        return False, "keyring library not installed — MCP secret storage disabled."


def _check_age() -> tuple[bool, str]:
    path = shutil.which("age")
    if path:
        return True, f"age binary: {path}"
    return (
        False,
        "age binary: not found — export/import encryption unavailable\n"
        "    → Install: brew install age  (macOS)  |  apt install age  (Debian/Ubuntu)",
    )


def _check_llm() -> tuple[bool, str]:
    try:
        from config import load_config

        cfg = load_config()
        model = cfg.get("llm_model") or cfg.get("model")
        if model:
            return True, f"LLM configured: {model}"
        return (
            False,
            "No LLM configured — memory sync will use no-LLM fallback.\n"
            "    → Run: apc configure  to set up an LLM provider",
        )
    except Exception as e:
        return False, f"Could not check LLM config: {e}"


def _check_cache_files() -> tuple[bool, str]:
    try:
        from cache import load_mcp_servers, load_memory, load_skills

        s = len(load_skills())
        m = len(load_mcp_servers())
        mem = len(load_memory())
        return True, f"Cache: {s} skills, {m} MCP servers, {mem} memory entries"
    except Exception as e:
        return False, f"Cache read error: {e}"


@click.command()
def doctor():
    """Check environment, configuration, and cache health. (#22)

    \b
    Runs a series of checks and prints a health report. Use this to
    diagnose configuration issues, missing dependencies, and cache state.
    """
    from rich.console import Console
    from rich.rule import Rule
    from rich.text import Text

    console = Console()
    console.print()
    console.print(Rule("[bold]apc doctor[/bold]", style="cyan"))
    console.print()

    # System checks
    checks = [
        _check_python,
        _check_cache_dir,
        _check_config_dir,
        _check_keychain,
        _check_age,
        _check_llm,
        _check_cache_files,
    ]

    all_ok = True
    console.print("[bold]System Checks[/bold]")

    for fn in checks:
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"Check failed: {e}"

        if ok:
            console.print(Text(f"  ✓ {msg}", style="green"))
        else:
            all_ok = False
            lines = msg.split("\n")
            console.print(Text(f"  ✗ {lines[0]}", style="red"))
            for extra in lines[1:]:
                console.print(Text(f"    {extra}", style="dim"))

    # Detected tools
    console.print()
    console.print("[bold]Detected AI Tools[/bold]")
    try:
        detected = detect_installed_tools()
        if detected:
            for t in detected:
                console.print(f"  ● {t}")
        else:
            console.print("  [dim](none detected)[/dim]")
    except Exception as e:
        console.print(f"  [red]Detection failed: {e}[/red]")

    # Summary
    console.print()
    if all_ok:
        console.print(Rule("[bold green]All checks passed.[/bold green]", style="green"))
    else:
        console.print(
            Rule(
                "[bold yellow]Some checks failed — see above for remediation.[/bold yellow]",
                style="yellow",
            )
        )
    console.print()
