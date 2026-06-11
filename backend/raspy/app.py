"""Uvicorn entry point: ``uvicorn raspy.app:app``."""

from __future__ import annotations

from .core.app import create_app

app = create_app()
