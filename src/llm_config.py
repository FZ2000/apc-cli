"""LLM provider configuration — auth profiles, models config, interactive wizard.

Stores auth profiles at ~/.apc/auth-profiles.json and model config at
~/.apc/models.json.  Supports multiple providers with multi-version,
multi-auth configuration.

The interactive wizard guides users with per-provider help text, API key
URLs, and setup instructions (pattern copied from OpenClaw's configure).
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from rich.panel import Panel
from rich.table import Table

from config import get_config_dir
from ui import console

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


@dataclass
class ProviderDef:
    name: str
    auth_methods: List[str]
    env_var: Optional[str]
    base_url: str
    api_dialect: str  # "anthropic-messages" | "openai-completions"
    default_models: List[str] = field(default_factory=list)
    hint: str = ""  # Short hint shown next to provider name in selection


PROVIDERS: Dict[str, ProviderDef] = {
    "anthropic": ProviderDef(
        name="Anthropic",
        auth_methods=["api_key", "token"],
        env_var="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com",
        api_dialect="anthropic-messages",
        default_models=["claude-sonnet-4-6", "claude-haiku-4-5"],
        hint="setup-token + API key",
    ),
    "openai": ProviderDef(
        name="OpenAI",
        auth_methods=["api_key"],
        env_var="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        api_dialect="openai-completions",
        default_models=["gpt-4o", "gpt-4o-mini"],
        hint="API key",
    ),
    "gemini": ProviderDef(
        name="Google Gemini",
        auth_methods=["api_key"],
        env_var="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_dialect="openai-completions",
        default_models=["gemini-2.5-pro", "gemini-2.0-flash"],
        hint="API key",
    ),
    "qwen": ProviderDef(
        name="Qwen (Alibaba)",
        auth_methods=["api_key"],
        env_var="DASHSCOPE_API_KEY",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_dialect="openai-completions",
        default_models=["qwen-max", "qwen-plus"],
        hint="API key",
    ),
    "glm": ProviderDef(
        name="GLM (Z.AI / Zhipu)",
        auth_methods=["api_key"],
        env_var="ZAI_API_KEY",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_dialect="openai-completions",
        default_models=["glm-4-plus", "glm-4-flash"],
        hint="API key",
    ),
    "minimax": ProviderDef(
        name="MiniMax",
        auth_methods=["api_key"],
        env_var="MINIMAX_API_KEY",
        base_url="https://api.minimax.chat/v1",
        api_dialect="openai-completions",
        default_models=["MiniMax-Text-01", "abab6.5s-chat"],
        hint="API key",
    ),
    "kimi": ProviderDef(
        name="Kimi (Moonshot)",
        auth_methods=["api_key"],
        env_var="MOONSHOT_API_KEY",
        base_url="https://api.moonshot.cn/v1",
        api_dialect="openai-completions",
        default_models=["moonshot-v1-8k", "moonshot-v1-32k"],
        hint="API key",
    ),
    "custom": ProviderDef(
        name="Custom Provider",
        auth_methods=["api_key"],
        env_var=None,
        base_url="",
        api_dialect="openai-completions",
        default_models=[],
        hint="Any OpenAI or Anthropic compatible endpoint",
    ),
}

AUTH_METHOD_LABELS = {
    "api_key": "API Key",
    "token": "Anthropic token (paste setup-token)",
}

# ---------------------------------------------------------------------------
# Per-provider guidance text (copied from OpenClaw's configure patterns)
# ---------------------------------------------------------------------------

# Shown as a note panel before prompting for credentials
PROVIDER_GUIDANCE: Dict[str, Dict[str, str]] = {
    "anthropic": {
        "api_key": (
            "Get your API key at: https://console.anthropic.com/settings/keys\n"
            "Or set the ANTHROPIC_API_KEY environment variable."
        ),
        "token": (
            "Run `claude setup-token` in your terminal.\n"
            "Then paste the generated token below.\n"
            "\n"
            "This uses Claude's OAuth setup-token flow — no API key needed."
        ),
    },
    "openai": {
        "api_key": (
            "Get your API key at: https://platform.openai.com/api-keys\n"
            "Or set the OPENAI_API_KEY environment variable."
        ),
    },
    "gemini": {
        "api_key": (
            "Get your API key at: https://aistudio.google.com/apikey\n"
            "Or set the GEMINI_API_KEY environment variable."
        ),
    },
    "qwen": {
        "api_key": (
            "Get your API key at: https://bailian.console.aliyun.com/?apiKey=1\n"
            "Or set the DASHSCOPE_API_KEY environment variable.\n"
            "\n"
            "Qwen uses Alibaba's DashScope API with OpenAI-compatible endpoints."
        ),
    },
    "glm": {
        "api_key": (
            "Get your API key at: https://open.bigmodel.cn/usercenter/apikeys\n"
            "Or set the ZAI_API_KEY environment variable.\n"
            "\n"
            "Z.AI provides GLM models (Zhipu AI). Uses OpenAI-compatible endpoints."
        ),
    },
    "minimax": {
        "api_key": (
            "Get your API key at: https://platform.minimaxi.com/user-center/basic-information/interface-key\n"
            "Or set the MINIMAX_API_KEY environment variable."
        ),
    },
    "kimi": {
        "api_key": (
            "Get your API key at: https://platform.moonshot.cn/console/api-keys\n"
            "Or set the MOONSHOT_API_KEY environment variable.\n"
            "\n"
            "Kimi is powered by Moonshot AI. Uses OpenAI-compatible endpoints."
        ),
    },
    "custom": {
        "api_key": (
            "Configure any OpenAI-compatible or Anthropic-compatible endpoint.\n"
            "Works with local servers (Ollama, vLLM, LM Studio) or any proxy.\n"
            "\n"
            "Default Ollama URL: http://127.0.0.1:11434/v1"
        ),
    },
}

# API key prompt labels per provider
PROVIDER_KEY_PROMPTS: Dict[str, str] = {
    "anthropic": "Enter Anthropic API key",
    "openai": "Enter OpenAI API key",
    "gemini": "Enter Gemini API key",
    "qwen": "Enter DashScope API key",
    "glm": "Enter Z.AI API key",
    "minimax": "Enter MiniMax API key",
    "kimi": "Enter Moonshot API key",
    "custom": "API Key (leave blank if not required)",
}

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------


def _auth_profiles_path() -> Path:
    return get_config_dir() / "auth-profiles.json"


def _models_path() -> Path:
    return get_config_dir() / "models.json"


# ---------------------------------------------------------------------------
# Auth profile CRUD
# ---------------------------------------------------------------------------


def load_auth_profiles() -> Dict[str, Any]:
    path = _auth_profiles_path()
    if not path.exists():
        return {"version": 1, "profiles": {}, "order": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") == 1:
            return data
    except (json.JSONDecodeError, IOError):
        pass
    return {"version": 1, "profiles": {}, "order": {}}


def save_auth_profiles(data: Dict[str, Any]) -> None:
    path = _auth_profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_auth_profile(
    provider: str,
    profile_name: str,
    auth_type: str,
    **kwargs: str,
) -> str:
    """Add or update an auth profile.  Returns the profile key."""
    data = load_auth_profiles()
    key = f"{provider}:{profile_name}"
    profile: Dict[str, Any] = {
        "type": auth_type,
        "provider": provider,
    }
    profile.update(kwargs)
    data["profiles"][key] = profile

    # Update order
    order_list = data.setdefault("order", {}).setdefault(provider, [])
    if key not in order_list:
        order_list.append(key)

    save_auth_profiles(data)
    return key


def remove_auth_profile(profile_key: str) -> bool:
    """Remove an auth profile by key.  Returns True if found and removed."""
    data = load_auth_profiles()
    if profile_key not in data["profiles"]:
        return False
    provider = data["profiles"][profile_key].get("provider", "")
    del data["profiles"][profile_key]
    # Clean up order
    if provider in data.get("order", {}):
        data["order"][provider] = [k for k in data["order"][provider] if k != profile_key]
        if not data["order"][provider]:
            del data["order"][provider]
    save_auth_profiles(data)
    return True


def get_auth_profile(profile_key: str) -> Optional[Dict[str, Any]]:
    """Get a single auth profile by key."""
    data = load_auth_profiles()
    return data["profiles"].get(profile_key)


def get_default_profile_for_provider(provider: str) -> Optional[Dict[str, Any]]:
    """Get the first (default) auth profile for a provider."""
    data = load_auth_profiles()
    order = data.get("order", {}).get(provider, [])
    if order:
        return data["profiles"].get(order[0])
    # Fallback: find any profile for this provider
    for key, profile in data["profiles"].items():
        if profile.get("provider") == provider:
            return profile
    return None


def resolve_api_key(provider: str, profile_key: Optional[str] = None) -> Optional[str]:
    """Resolve an API key for a provider: explicit profile > saved profile > env var."""
    # 1. Explicit profile
    if profile_key:
        profile = get_auth_profile(profile_key)
        if profile:
            return profile.get("key") or profile.get("token")

    # 2. Default saved profile
    profile = get_default_profile_for_provider(provider)
    if profile:
        key = profile.get("key") or profile.get("token")
        if key:
            return key

    # 3. Env var fallback
    pdef = PROVIDERS.get(provider)
    if pdef and pdef.env_var:
        return os.environ.get(pdef.env_var)

    return None


def resolve_auth_type(provider: str, profile_key: Optional[str] = None) -> str:
    """Resolve the auth type for a provider. Returns 'token', 'api_key', or 'api_key' as default."""
    if profile_key:
        profile = get_auth_profile(profile_key)
        if profile:
            return profile.get("type", "api_key")

    profile = get_default_profile_for_provider(provider)
    if profile:
        return profile.get("type", "api_key")

    return "api_key"


# ---------------------------------------------------------------------------
# Models config CRUD
# ---------------------------------------------------------------------------


def load_models_config() -> Dict[str, Any]:
    path = _models_path()
    if not path.exists():
        return {"default": None, "fallbacks": [], "providers": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {"default": None, "fallbacks": [], "providers": {}}


def save_models_config(data: Dict[str, Any]) -> None:
    path = _models_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def set_default_model(model_id: str) -> None:
    """Set the default model.  model_id format: 'provider/model-name'."""
    data = load_models_config()
    data["default"] = model_id
    save_models_config(data)


def get_default_model() -> Optional[str]:
    """Get the configured default model (e.g. 'anthropic/claude-sonnet-4-6')."""
    return load_models_config().get("default")


def ensure_provider_in_models(
    provider: str, base_url: str, api_dialect: str, models: List[str]
) -> None:
    """Ensure a provider entry exists in models.json."""
    data = load_models_config()
    if provider not in data.get("providers", {}):
        data.setdefault("providers", {})[provider] = {
            "baseUrl": base_url,
            "api": api_dialect,
            "models": models,
        }
        save_models_config(data)


def resolve_model() -> Optional[Dict[str, Any]]:
    """Resolve the model to use.  Returns {provider, model, api_dialect, base_url} or None."""
    default = get_default_model()
    if not default:
        return None

    if "/" not in default:
        return None

    provider, model = default.split("/", 1)
    pdef = PROVIDERS.get(provider)
    models_cfg = load_models_config()
    provider_cfg = models_cfg.get("providers", {}).get(provider, {})

    base_url = provider_cfg.get("baseUrl") or (pdef.base_url if pdef else "")
    api_dialect = provider_cfg.get("api") or (pdef.api_dialect if pdef else "openai-completions")

    return {
        "provider": provider,
        "model": model,
        "api_dialect": api_dialect,
        "base_url": base_url,
    }


# ---------------------------------------------------------------------------
# Helper: show guidance panel
# ---------------------------------------------------------------------------


def _show_guidance(provider: str, auth_method: str) -> None:
    """Display provider-specific setup guidance in a panel."""
    guidance = PROVIDER_GUIDANCE.get(provider, {}).get(auth_method)
    if not guidance:
        return
    pdef = PROVIDERS.get(provider)
    title = pdef.name if pdef else provider
    console.print()
    console.print(
        Panel(
            guidance,
            title=f"[bold]{title}[/bold]",
            border_style="blue",
            padding=(1, 2),
        )
    )


def _check_env_var(provider: str) -> Optional[str]:
    """Check if the provider's env var is already set. Returns the value or None."""
    pdef = PROVIDERS.get(provider)
    if pdef and pdef.env_var:
        val = os.environ.get(pdef.env_var)
        if val:
            return val
    return None


def _prompt_secret(label: str, allow_empty: bool = False) -> str:
    """Prompt for a secret value with hidden input and receipt confirmation.

    Shows a notice that input is hidden, then confirms how many characters
    were received so the user knows the paste worked.
    """
    console.print("[dim]  (input is hidden)[/dim]")
    value = click.prompt(label, hide_input=True, default="" if allow_empty else None)
    if value:
        # Show masked receipt so user knows it worked
        if len(value) <= 8:
            masked = "*" * len(value)
        else:
            masked = value[:4] + "*" * (len(value) - 8) + value[-4:]
        console.print(f"[dim]  Received {len(value)} chars: {masked}[/dim]")
    elif not allow_empty:
        console.print("[yellow]  No input received.[/yellow]")
    return value


# ---------------------------------------------------------------------------
# Interactive configure wizard
# ---------------------------------------------------------------------------


def _prompt_provider() -> str:
    """Interactive provider selection with hints."""
    choices = list(PROVIDERS.keys())

    console.print()
    console.print("[bold]? Select a provider:[/bold]")
    for i, key in enumerate(choices, 1):
        pdef = PROVIDERS[key]
        hint = f"  [dim]{pdef.hint}[/dim]" if pdef.hint else ""
        console.print(f"  [bold cyan]{i}.[/bold cyan] {pdef.name}{hint}")
    console.print()

    while True:
        raw = click.prompt("Enter number", type=int)
        if 1 <= raw <= len(choices):
            return choices[raw - 1]
        console.print("[red]Invalid choice.[/red]")


def _prompt_auth_method(provider: str) -> str:
    """Interactive auth method selection with descriptions."""
    pdef = PROVIDERS[provider]
    methods = pdef.auth_methods

    if len(methods) == 1:
        return methods[0]

    console.print()
    console.print(f"[bold]? Authentication method for {pdef.name}:[/bold]")
    for i, method in enumerate(methods, 1):
        label = AUTH_METHOD_LABELS.get(method, method)
        # Add hints for each method
        if method == "token" and provider == "anthropic":
            hint = "  [dim]run `claude setup-token` elsewhere, then paste the token here[/dim]"
        elif method == "api_key":
            hint = ""
        else:
            hint = ""
        console.print(f"  [bold cyan]{i}.[/bold cyan] {label}{hint}")
    console.print()

    while True:
        raw = click.prompt("Enter number", type=int)
        if 1 <= raw <= len(methods):
            return methods[raw - 1]
        console.print("[red]Invalid choice.[/red]")


def _prompt_model_selection(provider: str, pdef: ProviderDef) -> Optional[str]:
    """Let user pick from default models or enter a custom model ID."""
    models = pdef.default_models
    if not models:
        return None

    console.print()
    console.print(f"[bold]? Select default model for {pdef.name}:[/bold]")
    for i, model in enumerate(models, 1):
        console.print(f"  [bold cyan]{i}.[/bold cyan] {provider}/{model}")
    console.print(f"  [bold cyan]{len(models) + 1}.[/bold cyan] Enter model manually")
    console.print()

    while True:
        raw = click.prompt("Enter number", type=int, default=1)
        if 1 <= raw <= len(models):
            return models[raw - 1]
        if raw == len(models) + 1:
            return click.prompt("Enter model ID (e.g. claude-sonnet-4-6)")
        console.print("[red]Invalid choice.[/red]")


def configure_interactive() -> None:
    """Run the interactive configure wizard with user guidance."""
    provider = _prompt_provider()
    pdef = PROVIDERS[provider]
    auth_method = _prompt_auth_method(provider)

    # Show setup guidance
    _show_guidance(provider, auth_method)

    kwargs: Dict[str, str] = {}

    # --- Custom provider flow ---
    if provider == "custom":
        console.print()
        base_url = click.prompt(
            "API Base URL",
            default="http://127.0.0.1:11434/v1",
        )

        # Detect endpoint compatibility
        console.print()
        console.print("[bold]? Endpoint compatibility:[/bold]")
        console.print(
            "  [bold cyan]1.[/bold cyan] OpenAI-compatible  [dim]Uses /chat/completions[/dim]"
        )
        console.print("  [bold cyan]2.[/bold cyan] Anthropic-compatible  [dim]Uses /messages[/dim]")
        console.print()
        compat = click.prompt("Enter number", type=int, default=1)
        api_dialect = "anthropic-messages" if compat == 2 else "openai-completions"

        model_id = click.prompt("Model ID", type=str)

        # API key (optional for local)
        env_key = _check_env_var(provider)
        if env_key:
            console.print("[bold green]✓[/bold green] Found API key in environment")
            kwargs["key"] = env_key
        else:
            key = _prompt_secret(
                PROVIDER_KEY_PROMPTS.get(provider, "Enter API key"),
                allow_empty=True,
            )
            if key:
                kwargs["key"] = key

        profile_name = click.prompt("Profile name", default="default")
        key_str = add_auth_profile(provider, profile_name, auth_method, **kwargs)
        console.print(f'[bold green]✓[/bold green] Saved auth profile "{key_str}"')

        models = [model_id] if model_id else []
        ensure_provider_in_models(provider, base_url, api_dialect, models)

        if model_id:
            full_model_id = f"{provider}/{model_id}"
            set_default_model(full_model_id)
            console.print(
                f"[bold green]✓[/bold green] Default model set to [cyan]{full_model_id}[/cyan]"
            )
        return

    # --- Standard provider flow ---

    # Check env var first
    env_key = _check_env_var(provider)
    if env_key and auth_method == "api_key":
        console.print(f"[bold green]✓[/bold green] Found {pdef.env_var} in environment")
        if click.confirm(f"Use {pdef.env_var} from environment?", default=True):
            kwargs["key"] = env_key
        else:
            env_key = None

    if not env_key or auth_method != "api_key":
        if auth_method == "api_key":
            key = _prompt_secret(
                PROVIDER_KEY_PROMPTS.get(provider, f"Enter {pdef.name} API key"),
            )
            kwargs["key"] = key
        elif auth_method == "token":
            token = _prompt_secret("Paste Anthropic setup-token")
            kwargs["token"] = token
            token_name = click.prompt("Token name", default="default")
            kwargs["token_name"] = token_name

    profile_name = click.prompt("Profile name", default="default")

    # Save auth profile
    key_str = add_auth_profile(provider, profile_name, auth_method, **kwargs)
    console.print(f'[bold green]✓[/bold green] Saved auth profile "{key_str}"')

    # Ensure provider in models config
    ensure_provider_in_models(provider, pdef.base_url, pdef.api_dialect, pdef.default_models)

    # Model selection
    model_id = _prompt_model_selection(provider, pdef)
    if model_id:
        full_model_id = f"{provider}/{model_id}"
        set_default_model(full_model_id)
        console.print(
            f"[bold green]✓[/bold green] Default model set to [cyan]{full_model_id}[/cyan]"
        )

    # Done — show summary
    console.print()
    console.print(
        Panel(
            f"Provider: [cyan]{pdef.name}[/cyan]\n"
            f"Auth: {AUTH_METHOD_LABELS.get(auth_method, auth_method)}\n"
            f"Profile: [cyan]{key_str}[/cyan]\n"
            f"Model: [cyan]{provider}/{model_id or '(none)'}[/cyan]",
            title="[bold]Configuration complete[/bold]",
            border_style="green",
            padding=(1, 2),
        )
    )


def configure_non_interactive(
    provider: str,
    auth_method: str = "api_key",
    api_key: Optional[str] = None,
    token: Optional[str] = None,
    base_url: Optional[str] = None,
    model_id: Optional[str] = None,
    profile_name: str = "default",
    set_default: bool = True,
) -> str:
    """Non-interactive configure.  Returns the profile key."""
    if provider not in PROVIDERS:
        raise click.ClickException(f"Unknown provider: {provider}")

    pdef = PROVIDERS[provider]

    kwargs: Dict[str, str] = {}
    if auth_method == "api_key" and api_key:
        kwargs["key"] = api_key
    elif auth_method == "token" and token:
        kwargs["token"] = token

    key = add_auth_profile(provider, profile_name, auth_method, **kwargs)

    actual_base_url = base_url or pdef.base_url
    actual_models = [model_id] if model_id else pdef.default_models
    ensure_provider_in_models(provider, actual_base_url, pdef.api_dialect, actual_models)

    if set_default:
        m = model_id or (pdef.default_models[0] if pdef.default_models else None)
        if m:
            set_default_model(f"{provider}/{m}")

    return key


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@click.command("configure")
@click.option("--provider", default=None, help="Provider name (e.g. anthropic, openai)")
@click.option("--auth-method", default="api_key", help="Auth method: api_key, token")
@click.option("--api-key", default=None, help="API key for non-interactive setup")
@click.option("--token", default=None, help="Setup token for non-interactive setup")
@click.option("--base-url", default=None, help="Custom base URL")
@click.option("--model-id", default=None, help="Model ID (e.g. claude-sonnet-4-6)")
@click.option("--profile-name", default="default", help="Auth profile name")
@click.option("--non-interactive", is_flag=True, help="Run in non-interactive mode")
def configure_cmd(
    provider, auth_method, api_key, token, base_url, model_id, profile_name, non_interactive
):
    """Configure an LLM provider for APC memory sync.

    \b
    Interactive:
      apc configure

    \b
    Non-interactive:
      apc configure --provider anthropic --api-key "$ANTHROPIC_API_KEY"
      apc configure --provider openai --api-key "$OPENAI_API_KEY"
      apc configure --provider custom --base-url "http://localhost:4000/v1" \\
        --api-key "$KEY" --model-id "llama-3"
    """
    if non_interactive or provider:
        if not provider:
            raise click.ClickException("--provider is required in non-interactive mode")
        key = configure_non_interactive(
            provider=provider,
            auth_method=auth_method,
            api_key=api_key,
            token=token,
            base_url=base_url,
            model_id=model_id,
            profile_name=profile_name,
        )
        console.print(f'[bold green]✓[/bold green] Saved auth profile "{key}"')
    else:
        configure_interactive()


@click.group("model")
def models_cmd():
    """Manage LLM model configuration."""
    pass


@models_cmd.command("status")
def models_status():
    """Show default model and auth profile status."""
    default = get_default_model()
    profiles = load_auth_profiles()

    console.print()
    if default:
        console.print(f"[bold]Default model:[/bold] [cyan]{default}[/cyan]")
    else:
        console.print("[bold]Default model:[/bold] [dim]not configured[/dim]")

    profile_count = len(profiles.get("profiles", {}))
    console.print(f"[bold]Auth profiles:[/bold] {profile_count} configured")

    # Show profiles
    for pkey, prof in profiles.get("profiles", {}).items():
        auth_type = prof.get("type", "?")
        has_key = bool(prof.get("key") or prof.get("token"))
        status = "[green]active[/green]" if has_key else "[yellow]no credentials[/yellow]"
        console.print(f"  {pkey} ({auth_type}) — {status}")

    if not default:
        console.print()
        console.print("[dim]Run 'apc configure' to set up an LLM provider.[/dim]")


@models_cmd.command("list")
def models_list():
    """List configured providers and models."""
    models_cfg = load_models_config()
    profiles = load_auth_profiles()

    table = Table(title="Configured Providers", show_lines=False)
    table.add_column("Provider", style="cyan")
    table.add_column("Base URL", style="dim")
    table.add_column("API Dialect", style="dim")
    table.add_column("Models")
    table.add_column("Auth", justify="center")

    providers = models_cfg.get("providers", {})
    if not providers:
        console.print("[dim]No providers configured. Run 'apc configure' first.[/dim]")
        return

    for pname, pcfg in providers.items():
        model_list = ", ".join(pcfg.get("models", []))
        # Check if auth exists
        has_auth = any(p.get("provider") == pname for p in profiles.get("profiles", {}).values())
        auth_badge = "[green]yes[/green]" if has_auth else "[red]no[/red]"
        table.add_row(
            pname,
            pcfg.get("baseUrl", ""),
            pcfg.get("api", ""),
            model_list,
            auth_badge,
        )

    console.print()
    console.print(table)

    default = get_default_model()
    if default:
        console.print(f"\n[bold]Default:[/bold] [cyan]{default}[/cyan]")


@models_cmd.command("set")
@click.argument("model")
def models_set(model):
    """Set the default model (e.g. 'anthropic/claude-sonnet-4-6')."""
    if "/" not in model:
        raise click.ClickException(
            "Model must be in 'provider/model' format (e.g. 'anthropic/claude-sonnet-4-6')"
        )
    set_default_model(model)
    console.print(f"[bold green]✓[/bold green] Default model set to [cyan]{model}[/cyan]")


@models_cmd.group("auth")
def models_auth():
    """Manage auth profiles."""
    pass


@models_auth.command("add")
@click.option("--provider", required=True, help="Provider name")
@click.option("--auth-method", default="api_key", help="Auth method")
@click.option("--api-key", default=None, help="API key")
@click.option("--profile-name", default="default", help="Profile name")
def models_auth_add(provider, auth_method, api_key, profile_name):
    """Add an auth profile."""
    pdef = PROVIDERS.get(provider)
    if not pdef:
        raise click.ClickException(f"Unknown provider: {provider}")

    kwargs = {}
    if auth_method == "api_key":
        if not api_key:
            # Show guidance
            _show_guidance(provider, auth_method)
            api_key = _prompt_secret(
                PROVIDER_KEY_PROMPTS.get(provider, f"Enter {pdef.name} API key"),
            )
        kwargs["key"] = api_key
    elif auth_method == "token":
        _show_guidance(provider, auth_method)
        token = _prompt_secret("Paste Anthropic setup-token")
        kwargs["token"] = token

    key = add_auth_profile(provider, profile_name, auth_method, **kwargs)
    console.print(f'[bold green]✓[/bold green] Added auth profile "{key}"')


@models_auth.command("remove")
@click.argument("profile_key")
def models_auth_remove(profile_key):
    """Remove an auth profile (e.g. 'anthropic:default')."""
    if remove_auth_profile(profile_key):
        console.print(f'[bold green]✓[/bold green] Removed auth profile "{profile_key}"')
    else:
        console.print(f'[bold red]✗[/bold red] Profile "{profile_key}" not found')
