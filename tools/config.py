"""Shared, dependency-free configuration for the Zotero/Obsidian tools."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = {"zotero_data_dir": "ZOTERO_DATA_DIR"}
VAULT_DIRECTORIES = ("indexs", "notes", "templates")


def resolve_config_path(config_path: Path | None = None) -> Path:
    if config_path is not None:
        return config_path.expanduser().resolve()
    override = os.environ.get("OBSIDIAN_LITERATURE_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT / "config.toml"


def load_config(config_path: Path | None = None) -> dict[str, str]:
    path = resolve_config_path(config_path)
    values: dict[str, str] = {}
    if path.is_file():
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
        values.update(
            {
                key: str(value)
                for key, value in raw.get("paths", {}).items()
                if key in ENV_KEYS and value
            }
        )
    for key, env_name in ENV_KEYS.items():
        if os.environ.get(env_name):
            values[key] = os.environ[env_name]
    return values


def configured_path(key: str, config: dict[str, str]) -> Path | None:
    value = config.get(key)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def discover_vault_root(start: Path | None = None) -> Path:
    """Find the nearest project root containing the three literature directories."""
    current = (start or Path.cwd()).expanduser().resolve()
    for candidate in (current, *current.parents):
        if all((candidate / relative).is_dir() for relative in VAULT_DIRECTORIES):
            return candidate
    return current


def resolve_vault_root(explicit: Path | None = None, start: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    return discover_vault_root(start)
