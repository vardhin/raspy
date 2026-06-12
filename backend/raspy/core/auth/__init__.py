"""Authentication: brute-force-resistant login, rotating sessions, mini-PIN.

See plan/30-auth-security.md and plan/shiny-painting-flask (Layer 0). The package
mirrors core/notifications.py: a service object owns the tables + logic, a router
exposes the HTTP surface, and deps.py provides the FastAPI dependency that protects
routes. A CLI (raspy-auth) handles first-run account setup with no HTTP attack
surface.
"""

from __future__ import annotations

from .service import AuthService
from .deps import require_auth, optional_auth, Principal

__all__ = ["AuthService", "require_auth", "optional_auth", "Principal"]
