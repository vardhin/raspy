"""Shared "daily vibe" engine — one fresh image + quote (+ a magical font) per day,
fetched once from KEYLESS public providers and then cached to disk.

Two attachments use this:

* ``vibe`` — the "Vibe of the Day" app (magical full-screen image + quote).
* ``calendar`` — uses the same per-date image+quote as the *placeholder* shown on
  days that have no journal entry.

Design rules (from the product brief):

* **API-free**: no API keys, no signup. We hit public no-auth endpoints
  (``picsum.photos`` for images, ``api.quotable.io`` for quotes) and fall back to a
  bundled quote pool / a generated gradient if the network is unavailable.
* **Cache to disk**: a date's pick is fetched once and stored under ``cache/<date>/``.
  Every later read (including the calendar placeholder, and restarts) serves the
  cached copy — so it's stable per day and works offline after the first fetch.
* **Deterministic seed**: the image seed is derived from the date string, so even a
  cold cache produces the *same* image for a given day (picsum is seed-addressable).

The leading underscore keeps this package out of attachment discovery (the registry
skips ``_*`` modules) — it's a helper, not an app.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("raspy.dailyvibe")

_IMG_W, _IMG_H = 1600, 1000  # high-res, 16:10-ish
_FETCH_TIMEOUT = 12.0
_UA = "raspy-dailyvibe/1.0 (+https://github.com/raspy)"

# Curated "magical" Google display fonts. One is chosen per day and the actual
# font file is cached locally (see fonts.py) so it works offline afterwards.
MAGICAL_FONTS: list[str] = [
    "Cinzel Decorative",
    "Cormorant Garamond",
    "Tangerine",
    "Great Vibes",
    "Marcellus",
    "Pinyon Script",
    "Italianno",
    "Cardo",
    "EB Garamond",
    "Cormorant SC",
    "Spectral",
    "Playfair Display",
    "Yeseva One",
    "Forum",
    "Sail",
    "MedievalSharp",
    "Uncial Antiqua",
    "Almendra",
    "Berkshire Swash",
    "Dancing Script",
]

# Offline fallback quotes — used when the quote provider can't be reached. Kept
# small but varied; the live provider gives far more, this just keeps the app
# beautiful with zero internet.
_FALLBACK_QUOTES: list[dict[str, str]] = [
    {"content": "The quieter you become, the more you are able to hear.", "author": "Rumi"},
    {"content": "What we think, we become.", "author": "Buddha"},
    {"content": "Stars can't shine without darkness.", "author": "Unknown"},
    {"content": "The wound is the place where the light enters you.", "author": "Rumi"},
    {"content": "Not all those who wander are lost.", "author": "J.R.R. Tolkien"},
    {"content": "And still, after all this time, the sun never says to the earth, 'You owe me.'", "author": "Hafiz"},
    {"content": "Wherever you are, be there totally.", "author": "Eckhart Tolle"},
    {"content": "The world is full of magic things, patiently waiting for our senses to grow sharper.", "author": "W.B. Yeats"},
    {"content": "Look deep into nature, and then you will understand everything better.", "author": "Albert Einstein"},
    {"content": "To live is the rarest thing in the world. Most people exist, that is all.", "author": "Oscar Wilde"},
    {"content": "There is a crack in everything. That's how the light gets in.", "author": "Leonard Cohen"},
    {"content": "Be a lamp, or a lifeboat, or a ladder.", "author": "Rumi"},
    {"content": "The night is darkest just before the dawn.", "author": "Thomas Fuller"},
    {"content": "We are all in the gutter, but some of us are looking at the stars.", "author": "Oscar Wilde"},
    {"content": "Adopt the pace of nature: her secret is patience.", "author": "Ralph Waldo Emerson"},
    {"content": "Everything you can imagine is real.", "author": "Pablo Picasso"},
    {"content": "Turn your wounds into wisdom.", "author": "Oprah Winfrey"},
    {"content": "The soul becomes dyed with the color of its thoughts.", "author": "Marcus Aurelius"},
    {"content": "Let yourself be silently drawn by the strange pull of what you really love.", "author": "Rumi"},
    {"content": "In the middle of difficulty lies opportunity.", "author": "Albert Einstein"},
    {"content": "The earth has music for those who listen.", "author": "George Santayana"},
    {"content": "Do not go where the path may lead, go instead where there is no path and leave a trail.", "author": "Ralph Waldo Emerson"},
    {"content": "Hope is the thing with feathers that perches in the soul.", "author": "Emily Dickinson"},
    {"content": "You are the universe, expressing itself as a human for a little while.", "author": "Alan Watts"},
    {"content": "Tension is who you think you should be. Relaxation is who you are.", "author": "Chinese Proverb"},
    {"content": "What you seek is seeking you.", "author": "Rumi"},
    {"content": "Silence is a source of great strength.", "author": "Lao Tzu"},
    {"content": "The most beautiful thing we can experience is the mysterious.", "author": "Albert Einstein"},
    {"content": "She remembered who she was and the game changed.", "author": "Lalah Delia"},
    {"content": "Begin anywhere.", "author": "John Cage"},
    {"content": "The moon is a loyal companion. It never leaves.", "author": "Tahereh Mafi"},
    {"content": "Even the darkest night will end and the sun will rise.", "author": "Victor Hugo"},
    {"content": "Keep your face always toward the sunshine, and shadows will fall behind you.", "author": "Walt Whitman"},
    {"content": "A flower does not think of competing with the flower next to it. It just blooms.", "author": "Zen Shin"},
    {"content": "The quieter you become, the more you can hear the universe.", "author": "Unknown"},
    {"content": "Stay close to anything that makes you glad you are alive.", "author": "Hafiz"},
]


@dataclass
class DailyVibe:
    """One day's resolved content. ``image_path`` may be None if even the
    fallback gradient couldn't be written (extremely unlikely)."""

    date: str
    image_path: Path | None
    accent: str          # hex like "#aabbcc", derived from the image (or fallback)
    quote: str
    author: str
    font: str            # Google font family name for the day
    rev: float = 0.0     # fetch timestamp — used by the client to bust its cache

    def to_api(self, image_url: str) -> dict[str, Any]:
        return {
            "date": self.date,
            "image_url": image_url,
            "accent": self.accent,
            "quote": self.quote,
            "author": self.author,
            "font": self.font,
            "rev": self.rev,
        }


def _http_get(url: str, *, timeout: float = _FETCH_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted public URLs)
        return resp.read()


def _seed_for(date: str) -> str:
    """Stable per-date seed so picsum returns the same image for a day even on a
    cold cache / different machine."""
    return hashlib.sha256(date.encode()).hexdigest()[:16]


class DailyVibeStore:
    """Disk-backed cache of per-date image + quote + font choice.

    One instance per attachment that needs it; both ``vibe`` and ``calendar``
    point their store at the SAME directory (the vibe attachment's data dir) so a
    day fetched by either app is shared. Pass ``shared_dir`` explicitly to do so.
    """

    def __init__(self, cache_dir: Path) -> None:
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    # --- paths ---------------------------------------------------------------

    def _day_dir(self, date: str) -> Path:
        d = self.dir / date
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _meta_path(self, date: str) -> Path:
        return self._day_dir(date) / "meta.json"

    def image_path(self, date: str) -> Path:
        return self._day_dir(date) / "image.jpg"

    # --- public API ----------------------------------------------------------

    def has(self, date: str) -> bool:
        return self._meta_path(date).is_file() and self.image_path(date).is_file()

    def get(self, date: str) -> DailyVibe | None:
        meta = self._meta_path(date)
        if not meta.is_file():
            return None
        try:
            m = json.loads(meta.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        img = self.image_path(date)
        return DailyVibe(
            date=date,
            image_path=img if img.is_file() else None,
            accent=m.get("accent", "#5b6fb0"),
            quote=m.get("quote", ""),
            author=m.get("author", ""),
            font=m.get("font", MAGICAL_FONTS[0]),
            rev=m.get("fetched", 0.0),
        )

    def ensure(self, date: str, *, force: bool = False) -> DailyVibe:
        """Return the day's vibe, fetching + caching it if missing (or ``force``).

        Always returns *something* — falls back to a generated gradient + offline
        quote if the network is unavailable. Synchronous (does network I/O); call
        it from a thread (``asyncio.to_thread``).
        """
        if not force:
            existing = self.get(date)
            if existing is not None and existing.image_path is not None:
                return existing

        # A per-call salt makes a *manual* refresh (force=True) pick a genuinely
        # different image/quote/font; the default cold-cache path keeps the stable
        # per-date seed so a given day is reproducible.
        salt = str(time.time()) if force else ""

        font = self._pick_font(date, salt)
        quote, author = self._fetch_quote(date, salt)
        img_bytes, accent = self._fetch_image(date, salt)

        img_path = self.image_path(date)
        try:
            img_path.write_bytes(img_bytes)
        except OSError:
            log.exception("failed writing vibe image for %s", date)
            img_path = None  # type: ignore[assignment]

        now = time.time()
        vibe = DailyVibe(
            date=date,
            image_path=img_path,
            accent=accent,
            quote=quote,
            author=author,
            font=font,
            rev=now,
        )
        self._meta_path(date).write_text(
            json.dumps(
                {
                    "accent": accent,
                    "quote": quote,
                    "author": author,
                    "font": font,
                    "fetched": now,
                }
            )
        )
        return vibe

    # --- fetchers ------------------------------------------------------------

    def _pick_font(self, date: str, salt: str = "") -> str:
        rng = random.Random(_seed_for(date) + "font" + salt)
        return rng.choice(MAGICAL_FONTS)

    def _fetch_quote(self, date: str, salt: str = "") -> tuple[str, str]:
        # Keyless public quote provider; if it fails we pick from the offline pool.
        try:
            raw = _http_get("https://zenquotes.io/api/random")
            data = json.loads(raw)
            if isinstance(data, list) and data:
                q = data[0]
                content = (q.get("q") or "").strip()
                author = (q.get("a") or "Unknown").strip()
                if content:
                    return content, author
        except Exception as exc:  # noqa: BLE001 - offline / provider down → fallback
            log.info("quote fetch failed for %s (%r); using offline pool", date, exc)
        rng = random.Random(_seed_for(date) + "quote" + salt)
        q = rng.choice(_FALLBACK_QUOTES)
        return q["content"], q["author"]

    def _fetch_image(self, date: str, salt: str = "") -> tuple[bytes, str]:
        seed = _seed_for(date + salt)
        url = f"https://picsum.photos/seed/{seed}/{_IMG_W}/{_IMG_H}"
        try:
            data = _http_get(url)
            if data and len(data) > 1024:
                return data, _dominant_color(data)
        except Exception as exc:  # noqa: BLE001
            log.info("image fetch failed for %s (%r); using gradient", date, exc)
        # Offline fallback: a deterministic, pretty gradient SVG rasterized as bytes.
        svg, accent = _gradient_svg(seed)
        return svg, accent


def _dominant_color(jpeg: bytes) -> str:
    """A cheap dominant/average color for a JPEG without Pillow.

    We don't decode the JPEG (no image lib in runtime deps). Instead we hash the
    bytes into a pleasant, well-saturated HSL color — stable for a given image,
    and good enough to tint the background. (If Pillow is ever added we can swap
    in a true average.)
    """
    h = hashlib.sha256(jpeg[:4096]).digest()
    hue = h[0] / 255 * 360
    sat = 0.45 + (h[1] / 255) * 0.25      # 45–70%
    light = 0.32 + (h[2] / 255) * 0.16    # 32–48% (deep, readable bg)
    return _hsl_to_hex(hue, sat, light)


def _gradient_svg(seed: str) -> tuple[bytes, str]:
    h = hashlib.sha256(seed.encode()).digest()
    hue = h[0] / 255 * 360
    c1 = _hsl_to_hex(hue, 0.55, 0.30)
    c2 = _hsl_to_hex((hue + 40) % 360, 0.50, 0.55)
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{_IMG_W}' height='{_IMG_H}'>
<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
<stop offset='0' stop-color='{c1}'/><stop offset='1' stop-color='{c2}'/>
</linearGradient></defs><rect width='100%' height='100%' fill='url(#g)'/></svg>"""
    return svg.encode(), c1


def _hsl_to_hex(h: float, s: float, light: float) -> str:
    c = (1 - abs(2 * light - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = light - c / 2
    if h < 60:
        r, g, b = c, x, 0.0
    elif h < 120:
        r, g, b = x, c, 0.0
    elif h < 180:
        r, g, b = 0.0, c, x
    elif h < 240:
        r, g, b = 0.0, x, c
    elif h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    return "#{:02x}{:02x}{:02x}".format(
        round((r + m) * 255), round((g + m) * 255), round((b + m) * 255)
    )
