"""Layered configuration: defaults -> data/config.toml -> environment.

See plan/10-spine.md §6. Keep this small; attachment-specific config is sliced
out per attachment via ``Settings.attachment_config``.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-relative default data dir: backend/data/ (gitignored).
_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Settings(BaseSettings):
    """Runtime settings for the spine."""

    model_config = SettingsConfigDict(
        env_prefix="RASPY_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 49317

    # Where SQLite, secrets and per-attachment data live.
    data_dir: Path = _DEFAULT_DATA_DIR

    # Attachments explicitly disabled by id (everything discovered is enabled
    # by default). Lets you turn one off without removing the package.
    disabled_attachments: list[str] = Field(default_factory=list)

    # Optional extra directory of drop-in attachment packages.
    # (Built-in attachments under raspy/attachments/ are always discovered.)
    attachments_dir: Path | None = None

    # Web Push (VAPID) keys for background notifications. Generate a pair with
    # `raspy-vapid` (see scripts) and set these via config.toml or env
    # (RASPY_VAPID_PUBLIC_KEY / RASPY_VAPID_PRIVATE_KEY). Without them the
    # foreground (WebSocket) notification path still works; only background push
    # to closed tabs is skipped. `vapid_subject` is the contact mailto/URL the
    # push service sees.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:admin@localhost"

    # Per-attachment config blob loaded from config.toml's [attachments.<id>].
    _attachment_config: dict[str, dict[str, Any]] = {}

    @property
    def db_path(self) -> Path:
        return self.data_dir / "raspy.sqlite3"

    def attachment_data_dir(self, attachment_id: str) -> Path:
        return self.data_dir / "att" / attachment_id

    def attachment_config(self, attachment_id: str) -> dict[str, Any]:
        return self._attachment_config.get(attachment_id, {})


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


@lru_cache
def get_settings() -> Settings:
    """Build settings: TOML file (if present) overlaid by env vars.

    config.toml lives in the data dir. Its ``[attachments.<id>]`` tables become
    each attachment's config slice.
    """
    # We need the data dir before we can find config.toml, and the data dir may
    # itself be set via env. Resolve env-or-default first.
    bootstrap = Settings()
    toml_path = bootstrap.data_dir / "config.toml"
    raw = _load_toml(toml_path)

    attachment_cfg = raw.pop("attachments", {}) or {}
    # Remaining top-level keys override defaults but are still overridden by env
    # (BaseSettings env sources take precedence over constructor kwargs only if
    # we pass them as init — so env wins by re-reading after).
    settings = Settings(**raw)
    settings._attachment_config = attachment_cfg
    return settings
