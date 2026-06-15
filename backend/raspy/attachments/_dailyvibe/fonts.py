"""Local Google Fonts cache.

The vibe app wants a "magical font fetched from Google" per day, but we don't want
a hard runtime dependency on fonts.googleapis.com being reachable. So: fetch the
font's CSS + the actual font file ONCE from Google's keyless CSS API, store both on
disk, and serve them from the spine afterwards. After the first fetch a font works
fully offline.

Flow on the client:
  <link rel="stylesheet" href="/api/att/vibe/font.css?family=Great+Vibes">
which this module serves from cache (fetching on a miss). The CSS @font-face points
at /api/att/vibe/font-file/<hash>.woff2, also served from this cache. No API key.
"""

from __future__ import annotations

import hashlib
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("raspy.dailyvibe.fonts")

_CSS_API = "https://fonts.googleapis.com/css2"
# A modern UA so Google serves woff2 (smaller, well supported in our WebView/browser).
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
_TIMEOUT = 12.0
_FONT_URL_RE = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+)\)")


class FontCache:
    """Disk cache of Google font CSS + the woff2 files they reference."""

    def __init__(self, root: Path) -> None:
        self.css_dir = root / "css"
        self.file_dir = root / "files"
        self.css_dir.mkdir(parents=True, exist_ok=True)
        self.file_dir.mkdir(parents=True, exist_ok=True)

    # --- CSS -----------------------------------------------------------------

    def _css_path(self, family: str) -> Path:
        slug = hashlib.sha256(family.encode()).hexdigest()[:16]
        return self.css_dir / f"{slug}.css"

    def css(self, family: str) -> str:
        """Return cached (rewritten) CSS for ``family``, fetching on a miss.

        The returned CSS has its gstatic URLs rewritten to point at our own
        ``font-file/<hash>`` endpoint, and each referenced file is cached locally.
        Falls back to a bare CSS importing nothing useful only if the fetch fails
        (the client then just uses its default font).
        """
        path = self._css_path(family)
        if path.is_file():
            return path.read_text()

        try:
            css = self._fetch_css(family)
            css = self._localize(css)
            path.write_text(css)
            return css
        except Exception as exc:  # noqa: BLE001 - offline → empty css, client falls back
            log.info("font css fetch failed for %r (%r)", family, exc)
            return "/* font unavailable offline */"

    def _fetch_css(self, family: str) -> str:
        qs = urllib.parse.urlencode(
            {"family": f"{family}:wght@400;700", "display": "swap"}
        )
        req = urllib.request.Request(f"{_CSS_API}?{qs}", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            return resp.read().decode()

    def _localize(self, css: str) -> str:
        """Download each gstatic font file, cache it, and rewrite the url() to
        our own endpoint so the served CSS never reaches out to Google again."""

        def repl(m: re.Match[str]) -> str:
            src = m.group(1)
            digest = self._cache_file(src)
            return f"url(/api/att/vibe/font-file/{digest})"

        return _FONT_URL_RE.sub(repl, css)

    # --- font files ----------------------------------------------------------

    def _cache_file(self, url: str) -> str:
        digest = hashlib.sha256(url.encode()).hexdigest()[:24]
        path = self.file_dir / digest
        if not path.is_file():
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
                path.write_bytes(resp.read())
        return digest

    def file_path(self, digest: str) -> Path | None:
        # Digest is hex from our own naming; reject anything else (path safety).
        if not re.fullmatch(r"[0-9a-f]{1,64}", digest):
            return None
        p = self.file_dir / digest
        return p if p.is_file() else None
