"""Vibe of the Day — a magical daily image + quote.

Each day shows one high-res image and one quote, fetched once from KEYLESS public
providers and cached to disk (so it's stable per day and offline-resilient after the
first fetch). A random "magical" Google display font is chosen per day and cached
locally too. The frontend renders it with a sparkly star background and tints the
page with an accent color derived from the image.

The fetch+cache engine lives in ``raspy.attachments._dailyvibe`` and is *shared*:
the ``calendar`` attachment reuses the same per-date image+quote as the placeholder
on days with no journal entry. This attachment owns the cache directory; calendar
points its store at the same dir.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment

from .._dailyvibe import DailyVibeStore
from .._dailyvibe.fonts import FontCache


def _today() -> str:
    return dt.date.today().isoformat()


def _valid_date(s: str) -> str:
    try:
        dt.date.fromisoformat(s)
    except ValueError as exc:
        raise HTTPException(400, "invalid date (expected YYYY-MM-DD)") from exc
    return s


class Vibe(BaseAttachment):
    id = "vibe"
    title = "Vibe of the Day"
    icon = "sparkles"
    version = "1.0.0"

    store: DailyVibeStore
    fonts: FontCache

    async def on_load(self, ctx: AttachmentContext) -> None:
        # The shared cache dir. calendar will point at this same path.
        self.store = DailyVibeStore(ctx.data_dir / "cache")
        self.fonts = FontCache(ctx.data_dir / "fonts")
        # Warm today's vibe in the background so the first open is instant.
        asyncio.create_task(self._warm(_today()))

    async def _warm(self, date: str, *, force: bool = False) -> dict[str, Any]:
        vibe = await asyncio.to_thread(self.store.ensure, date, force=force)
        # Pre-cache the day's font file(s) too, off the event loop.
        await asyncio.to_thread(self.fonts.css, vibe.font)
        return vibe.to_api(self._image_url(date))

    def _image_url(self, date: str) -> str:
        # Relative to the attachment; the shell prefixes /api/att/vibe/.
        return f"image/{date}"

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/today")
        async def today() -> dict[str, Any]:
            return await self._warm(_today())

        @r.get("/day/{date}")
        async def day(date: str) -> dict[str, Any]:
            return await self._warm(_valid_date(date))

        @r.post("/refresh")
        async def refresh() -> dict[str, Any]:
            """Force a fresh image + quote for today (re-fetch + re-cache)."""
            out = await self._warm(_today(), force=True)
            self.events.publish("vibe.changed", {"date": _today()})
            return out

        @r.get("/image/{date}")
        async def image(date: str) -> Response:
            _valid_date(date)
            # Ensure the day exists (covers a direct hit before /today ran).
            await asyncio.to_thread(self.store.ensure, date)
            path: Path | None = self.store.image_path(date)
            if path is None or not path.is_file():
                raise HTTPException(404, "image not available")
            # Picsum gives JPEG; the gradient fallback is SVG. Sniff by leading byte.
            head = path.read_bytes()[:5]
            media = "image/svg+xml" if head.startswith(b"<svg") else "image/jpeg"
            return FileResponse(path, media_type=media)

        # --- local Google-font cache ----------------------------------------

        @r.get("/font.css")
        async def font_css(family: str) -> Response:
            css = await asyncio.to_thread(self.fonts.css, family)
            return Response(css, media_type="text/css")

        @r.get("/font-file/{digest}")
        async def font_file(digest: str) -> Response:
            path = self.fonts.file_path(digest)
            if path is None:
                raise HTTPException(404, "font file not found")
            return FileResponse(path, media_type="font/woff2")

        return r

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Vibe of the Day", children=[ui.vibe()])


attachment = Vibe()
