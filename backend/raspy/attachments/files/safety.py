"""Path confinement for the Files attachment.

Every filesystem path that comes from a client is untrusted. This module resolves
a client-supplied *relative* path against a fixed root and guarantees the result
stays inside that root — defeating both ``..`` traversal and symlink escapes by
resolving symlinks (``realpath``) before the containment check.

The root defaults to the operator's home directory (``~``); see plan/20 §7
(capabilities) and plan/30 (security). The attachment never operates above it.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException


class Confinement:
    """Resolves and validates paths under a single fixed root."""

    def __init__(self, root: Path) -> None:
        # Fully resolve the root once (follow symlinks, make absolute) so every
        # later comparison is against the canonical location.
        self.root = Path(os.path.realpath(root))

    def resolve(self, rel: str, *, must_exist: bool = False) -> Path:
        """Map a client path (relative to root) to a safe absolute path.

        ``rel`` is treated as relative to the root regardless of leading slashes.
        Raises 400 on traversal/escape, 404 when ``must_exist`` and it doesn't.
        """
        # Normalise: strip leading slashes so "/etc" can't jump to the real /etc,
        # and reject NUL bytes outright.
        cleaned = (rel or "").replace("\\", "/").lstrip("/")
        if "\x00" in cleaned:
            raise HTTPException(400, "invalid path")

        candidate = (self.root / cleaned)

        # realpath resolves any symlinks in the chain. We then require the result
        # to be the root itself or a descendant of it.
        resolved = Path(os.path.realpath(candidate))
        if resolved != self.root and self.root not in resolved.parents:
            raise HTTPException(400, "path escapes the allowed root")

        if must_exist and not resolved.exists():
            raise HTTPException(404, "not found")
        return resolved

    def to_rel(self, abs_path: Path) -> str:
        """Inverse of resolve: canonical absolute path -> client-facing rel path.

        Returns "" for the root, otherwise a POSIX-style relative path.
        """
        resolved = Path(os.path.realpath(abs_path))
        if resolved == self.root:
            return ""
        return resolved.relative_to(self.root).as_posix()
