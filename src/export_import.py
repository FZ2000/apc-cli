"""Export and import APC configs with age-encrypted secrets.

Export creates a portable directory of skills, MCP servers, memory, and config
that can be committed to a private repo and imported on another machine.
Secrets (API keys, MCP tokens) are encrypted with age (via pyrage) so they
stay safe even if the repo becomes public.
"""

import base64
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click

from cache import (
    load_local_bundle,
    load_mcp_servers,
    merge_mcp_servers,
    merge_memory,
    merge_skills,
    save_mcp_servers,
    save_memory,
    save_skills,
)
from config import get_config_dir
from secrets_manager import retrieve_secret, store_secrets_batch
from skills import get_skills_dir
from ui import error, header, info, success, warning

SCHEMA_VERSION = 1
AGE_PREFIX = "AGE:"
IDENTITY_FILENAME = "age-identity.txt"

# ---------------------------------------------------------------------------
# pyrage wrapper — graceful degradation when not installed
# ---------------------------------------------------------------------------

_pyrage_available: Optional[bool] = None


def _check_pyrage() -> bool:
    global _pyrage_available
    if _pyrage_available is None:
        try:
            import pyrage  # noqa: F401

            _pyrage_available = True
        except ImportError:
            _pyrage_available = False
    return _pyrage_available


def _identity_path() -> Path:
    return get_config_dir() / IDENTITY_FILENAME


def _load_or_create_identity() -> Tuple[str, str]:
    """Load or generate an age keypair.

    Returns (public_key, private_key_str).
    The private key is stored at ~/.apc/age-identity.txt (chmod 600).
    """
    from pyrage import x25519

    path = _identity_path()
    if path.exists():
        raw = path.read_text().strip()
        identity = x25519.Identity.from_str(raw)
        return str(identity.to_public()), raw

    identity = x25519.Identity.generate()
    private_str = str(identity)
    public_str = str(identity.to_public())

    path.write_text(private_str + "\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600

    return public_str, private_str


def _load_identity() -> Optional[str]:
    """Load the private key string from disk, or None if missing."""
    path = _identity_path()
    if not path.exists():
        return None
    return path.read_text().strip()


# ---------------------------------------------------------------------------
# Encrypt / decrypt helpers
# ---------------------------------------------------------------------------


def encrypt_value(value: str, public_key: str) -> str:
    """Encrypt a string with the age public key. Returns 'AGE:<base64>'."""
    from pyrage import encrypt, x25519

    recipient = x25519.Recipient.from_str(public_key)
    ciphertext = encrypt(value.encode(), [recipient])
    encoded = base64.b64encode(ciphertext).decode()
    return f"{AGE_PREFIX}{encoded}"


def decrypt_value(token: str, private_key_str: str) -> Optional[str]:
    """Decrypt an 'AGE:<base64>' token. Returns plaintext or None on failure."""
    from pyrage import decrypt, x25519

    if not token.startswith(AGE_PREFIX):
        return token  # not encrypted, pass through

    try:
        raw_b64 = token[len(AGE_PREFIX) :]
        ciphertext = base64.b64decode(raw_b64)
        identity = x25519.Identity.from_str(private_key_str)
        plaintext = decrypt(ciphertext, [identity])
        return plaintext.decode()
    except Exception:
        return None


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(AGE_PREFIX)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def _export_mcp_servers(servers: List[Dict], public_key: Optional[str]) -> List[Dict]:
    """Prepare MCP servers for export: encrypt secret values if key provided."""
    result = []
    for srv in servers:
        out = dict(srv)
        placeholders = srv.get("secret_placeholders", [])
        if placeholders and public_key:
            encrypted_secrets: Dict[str, str] = {}
            for key in placeholders:
                value = retrieve_secret("local", key)
                if value:
                    encrypted_secrets[key] = encrypt_value(value, public_key)
                else:
                    warning(f"Secret '{key}' not found in keychain, skipping")
            if encrypted_secrets:
                out["encrypted_secrets"] = encrypted_secrets
        result.append(out)
    return result


def _export_auth_profiles(data: Dict[str, Any], public_key: Optional[str]) -> Dict[str, Any]:
    """Encrypt key/token fields in auth profiles."""
    out = json.loads(json.dumps(data))  # deep copy
    for _pkey, profile in out.get("profiles", {}).items():
        for field in ("key", "token"):
            val = profile.get(field)
            if val and public_key:
                profile[field] = encrypt_value(val, public_key)
    return out


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------


def _import_mcp_servers(
    servers: List[Dict], private_key: Optional[str]
) -> Tuple[List[Dict], Dict[str, str]]:
    """Decrypt MCP server secrets and return (clean_servers, secrets_to_store)."""
    secrets_to_store: Dict[str, str] = {}
    result = []
    for srv in servers:
        out = dict(srv)
        enc = out.pop("encrypted_secrets", None)
        if enc and private_key:
            for key, cipher in enc.items():
                plain = decrypt_value(cipher, private_key)
                if plain:
                    secrets_to_store[key] = plain
                else:
                    warning(f"Failed to decrypt secret '{key}' for MCP server '{srv.get('name')}'")
        elif enc and not private_key:
            warning(f"Skipping encrypted secrets for '{srv.get('name')}' — no private key")
        result.append(out)
    return result, secrets_to_store


def _import_auth_profiles(data: Dict[str, Any], private_key: Optional[str]) -> Dict[str, Any]:
    """Decrypt key/token fields in auth profiles."""
    out = json.loads(json.dumps(data))  # deep copy
    for _pkey, profile in out.get("profiles", {}).items():
        for field in ("key", "token"):
            val = profile.get(field)
            if val and is_encrypted(val):
                if private_key:
                    plain = decrypt_value(val, private_key)
                    if plain:
                        profile[field] = plain
                    else:
                        warning(f"Failed to decrypt auth profile field '{field}'")
                        profile[field] = ""
                else:
                    warning(f"Skipping encrypted auth field '{field}' — no private key")
                    profile[field] = ""
    return out


# ---------------------------------------------------------------------------
# apc export
# ---------------------------------------------------------------------------


@click.command("export")
@click.argument("path", default="apc-export")
@click.option("--no-secrets", is_flag=True, help="Export without encrypting secrets")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def export_cmd(path: str, no_secrets: bool, yes: bool):
    """Export APC configs to a portable directory.

    Secrets are encrypted with age so the directory can be safely committed
    to a Git repo. Transfer your private key (~/.apc/age-identity.txt) to
    the target machine once via a secure channel.

    \b
    Examples:
      apc export                      # export to ./apc-export/
      apc export /tmp/my-config       # export to custom path
      apc export --no-secrets         # skip secret encryption
    """
    header("Export")
    export_dir = Path(path).resolve()

    # Load data
    bundle = load_local_bundle()
    skills = bundle["skills"]
    mcp_servers = load_mcp_servers()
    memory = bundle["memory"]

    skills_dir = get_skills_dir()
    config_dir = get_config_dir()

    # Summarise
    info(f"Export path: {export_dir}")
    info(f"Skills: {len(skills)}, MCP servers: {len(mcp_servers)}, Memory: {len(memory)}")

    # Count installed skills
    installed_skills: List[str] = []
    if skills_dir.exists():
        installed_skills = [
            d.name for d in sorted(skills_dir.iterdir()) if d.is_dir() and (d / "SKILL.md").exists()
        ]
    if installed_skills:
        info(f"Installed skills to copy: {len(installed_skills)}")

    # Config files
    auth_path = config_dir / "auth-profiles.json"
    models_path = config_dir / "models.json"
    marketplaces_path = config_dir / "marketplaces.json"

    has_auth = auth_path.exists()
    has_models = models_path.exists()
    has_marketplaces = marketplaces_path.exists()

    # Age key
    public_key: Optional[str] = None
    use_encryption = not no_secrets and _check_pyrage()

    if not no_secrets and not _check_pyrage():
        warning("pyrage not installed — exporting without secret encryption.")
        warning("Install with: pip install pyrage")
        use_encryption = False

    if use_encryption:
        public_key, _priv = _load_or_create_identity()
        info(f"Age public key: {public_key}")

    if not yes:
        if not click.confirm("\nProceed with export?"):
            info("Cancelled.")
            return

    # Create directory structure
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "cache").mkdir(exist_ok=True)
    (export_dir / "config").mkdir(exist_ok=True)

    # 1. Cache: skills.json (plain)
    (export_dir / "cache" / "skills.json").write_text(json.dumps(skills, indent=2, default=str))

    # 2. Cache: mcp_servers.json (with encrypted secrets)
    exported_mcp = _export_mcp_servers(mcp_servers, public_key)
    (export_dir / "cache" / "mcp_servers.json").write_text(
        json.dumps(exported_mcp, indent=2, default=str)
    )

    # 3. Cache: memory.json (plain)
    (export_dir / "cache" / "memory.json").write_text(json.dumps(memory, indent=2, default=str))

    # 4. Installed skills directory (resolve symlinks)
    if installed_skills:
        export_skills_dir = export_dir / "skills"
        if export_skills_dir.exists():
            shutil.rmtree(export_skills_dir)
        export_skills_dir.mkdir()
        for name in installed_skills:
            src = skills_dir / name
            dst = export_skills_dir / name
            shutil.copytree(src, dst, symlinks=False)

    # 5. Config files
    if has_marketplaces:
        shutil.copy2(marketplaces_path, export_dir / "config" / "marketplaces.json")

    if has_models:
        shutil.copy2(models_path, export_dir / "config" / "models.json")

    if has_auth:
        auth_data = json.loads(auth_path.read_text(encoding="utf-8"))
        exported_auth = _export_auth_profiles(auth_data, public_key)
        (export_dir / "config" / "auth-profiles.json").write_text(
            json.dumps(exported_auth, indent=2)
        )

    # 6. Metadata
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "public_key": public_key,
        "stats": {
            "skills": len(skills),
            "mcp_servers": len(mcp_servers),
            "memory": len(memory),
            "installed_skills": len(installed_skills),
        },
    }
    (export_dir / "apc-export.json").write_text(json.dumps(metadata, indent=2))

    success(f"Exported to {export_dir}")
    if public_key:
        info(f"Private key: {_identity_path()}")
        info("Transfer this key to the target machine to decrypt secrets.")


# ---------------------------------------------------------------------------
# apc import
# ---------------------------------------------------------------------------


@click.command("import")
@click.argument("path", default="apc-export")
@click.option("--no-secrets", is_flag=True, help="Skip secret decryption")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def import_cmd(path: str, no_secrets: bool, yes: bool):
    """Import APC configs from an export directory.

    Decrypts secrets using the age private key at ~/.apc/age-identity.txt.
    Transfer the key from the source machine before importing.

    \b
    Examples:
      apc import                      # import from ./apc-export/
      apc import /tmp/my-config       # import from custom path
      apc import --no-secrets         # skip secret decryption
    """
    header("Import")
    import_dir = Path(path).resolve()

    # Validate
    meta_path = import_dir / "apc-export.json"
    if not meta_path.exists():
        error(f"Not a valid export directory: {import_dir}")
        error("Expected apc-export.json metadata file.")
        raise SystemExit(1)

    metadata = json.loads(meta_path.read_text())
    schema = metadata.get("schema_version", 0)
    if schema > SCHEMA_VERSION:
        error(f"Export schema version {schema} is newer than supported ({SCHEMA_VERSION}).")
        error("Please upgrade APC: pip install --upgrade apc")
        raise SystemExit(1)

    # Load private key
    private_key: Optional[str] = None
    has_encrypted = metadata.get("public_key") is not None

    if has_encrypted and not no_secrets:
        if _check_pyrage():
            private_key = _load_identity()
            if not private_key:
                warning("Age private key not found at ~/.apc/age-identity.txt")
                warning("Transfer it from the source machine to decrypt secrets.")
                warning("Continuing without secret decryption.")
        else:
            warning("pyrage not installed — cannot decrypt secrets.")
            warning("Install with: pip install pyrage")

    stats = metadata.get("stats", {})
    info(f"Import path: {import_dir}")
    info(f"Created: {metadata.get('created_at', 'unknown')}")
    info(
        f"Skills: {stats.get('skills', 0)}, "
        f"MCP servers: {stats.get('mcp_servers', 0)}, "
        f"Memory: {stats.get('memory', 0)}"
    )
    if stats.get("installed_skills"):
        info(f"Installed skills: {stats['installed_skills']}")

    if not yes:
        if not click.confirm("\nProceed with import?"):
            info("Cancelled.")
            return

    config_dir = get_config_dir()

    # 1. Import skills cache
    skills_path = import_dir / "cache" / "skills.json"
    if skills_path.exists():
        new_skills = json.loads(skills_path.read_text())
        existing = load_local_bundle()["skills"]
        merged = merge_skills(existing, new_skills)
        save_skills(merged)
        success(f"Skills: {len(new_skills)} imported ({len(merged)} total)")

    # 2. Import memory cache
    memory_path = import_dir / "cache" / "memory.json"
    if memory_path.exists():
        new_memory = json.loads(memory_path.read_text())
        existing_mem = load_local_bundle()["memory"]
        merged_mem = merge_memory(existing_mem, new_memory)
        save_memory(merged_mem)
        success(f"Memory: {len(new_memory)} imported ({len(merged_mem)} total)")

    # 3. Import MCP servers cache (decrypt secrets)
    mcp_path = import_dir / "cache" / "mcp_servers.json"
    if mcp_path.exists():
        new_mcp = json.loads(mcp_path.read_text())
        clean_mcp, secrets = _import_mcp_servers(new_mcp, private_key)

        if secrets:
            store_secrets_batch("local", secrets)
            success(f"Stored {len(secrets)} secrets in keychain")

        existing_mcp = load_mcp_servers()
        merged_mcp = merge_mcp_servers(existing_mcp, clean_mcp)
        save_mcp_servers(merged_mcp)
        success(f"MCP servers: {len(new_mcp)} imported ({len(merged_mcp)} total)")

    # 4. Copy installed skills
    import_skills_dir = import_dir / "skills"
    if import_skills_dir.exists():
        skills_dir = get_skills_dir()
        skills_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for src in sorted(import_skills_dir.iterdir()):
            if src.is_dir() and (src / "SKILL.md").exists():
                dst = skills_dir / src.name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                count += 1
        if count:
            success(f"Installed skills: {count} copied to {skills_dir}")

    # 5. Import config files
    _import_config_file(
        import_dir / "config" / "marketplaces.json",
        config_dir / "marketplaces.json",
        "marketplaces.json",
    )
    _import_config_file(
        import_dir / "config" / "models.json",
        config_dir / "models.json",
        "models.json",
    )

    # Auth profiles (decrypt)
    auth_src = import_dir / "config" / "auth-profiles.json"
    if auth_src.exists():
        imported_auth = json.loads(auth_src.read_text())
        decrypted_auth = _import_auth_profiles(imported_auth, private_key)

        # Merge with existing
        auth_dst = config_dir / "auth-profiles.json"
        if auth_dst.exists():
            existing_auth = json.loads(auth_dst.read_text(encoding="utf-8"))
            # Merge profiles
            for pkey, profile in decrypted_auth.get("profiles", {}).items():
                existing_auth.setdefault("profiles", {})[pkey] = profile
            # Merge order
            for provider, order in decrypted_auth.get("order", {}).items():
                existing_order = existing_auth.setdefault("order", {}).setdefault(provider, [])
                for key in order:
                    if key not in existing_order:
                        existing_order.append(key)
            auth_dst.write_text(json.dumps(existing_auth, indent=2), encoding="utf-8")
        else:
            auth_dst.write_text(json.dumps(decrypted_auth, indent=2), encoding="utf-8")
        success("Imported auth-profiles.json")

    success("Import complete.")
    info("Run 'apc sync' to apply to your tools.")


def _import_config_file(src: Path, dst: Path, label: str) -> None:
    """Copy a config file if it exists in the export."""
    if src.exists():
        shutil.copy2(src, dst)
        success(f"Imported {label}")
