"""Calendar + vibe attachment tests.

The daily-vibe engine reaches out to keyless public providers; here we patch the
network so the suite is offline + deterministic. We exercise: entry CRUD, the
per-day range (entries vs. placeholders), image upload/serve, and that a due
reminder fires a notification via the durable scheduler.
"""

from __future__ import annotations

import datetime as dt
import io
import struct
import time
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from raspy.attachments import _dailyvibe
from raspy.config import Settings
from raspy.core.app import create_app

CAL = "/api/att/calendar"
VIBE = "/api/att/vibe"


def _png_bytes() -> bytes:
    """A tiny valid 1x1 PNG (so the upload's mime check passes)."""

    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + typ
            + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


@pytest.fixture
def cal_client(tmp_path: Path, monkeypatch):
    # Force the daily-vibe engine fully offline: image → gradient, quote → pool.
    monkeypatch.setattr(
        _dailyvibe, "_http_get", lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
    )
    from conftest import _seed_account
    from raspy.config import AuthSettings

    settings = Settings(
        data_dir=tmp_path,
        auth=AuthSettings(cookie_secure=False, argon_time_cost=1, argon_memory_kib=8, argon_parallelism=1),
    )
    _seed_account(settings)
    app = create_app(settings)
    with TestClient(app) as c:
        from raspy.core.auth import kdf

        auth_key = kdf.derive_auth_key("test-password", "PrXc0GEAlOveYCpyIegc0Q")
        r = c.post("/api/auth/login", json={"username": "tester", "auth_key": auth_key})
        assert r.status_code == 200, r.text
        c.headers.update({"X-CSRF-Token": r.json()["csrf_token"]})
        yield c


def test_attachments_in_manifest(cal_client: TestClient):
    ids = {a["id"] for a in cal_client.get("/api/manifest").json()["attachments"]}
    assert {"calendar", "vibe"} <= ids


def test_empty_day_has_placeholder(cal_client: TestClient):
    today = dt.date.today().isoformat()
    days = cal_client.get(CAL + "/range", params={"from": today, "to": today}).json()
    assert len(days) == 1
    day = days[0]
    assert day["date"] == today
    assert day["entries"] == []
    assert "placeholder" in day
    assert day["placeholder"]["quote"]  # offline pool still gives a quote
    assert day["placeholder"]["accent"].startswith("#")


def test_entry_crud_and_range(cal_client: TestClient):
    date = dt.date.today().isoformat()
    created = cal_client.post(
        CAL + "/entries",
        json={"date": date, "title": "Beach day", "description": "Sunny and warm."},
    )
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["title"] == "Beach day"

    days = cal_client.get(CAL + "/range", params={"from": date, "to": date}).json()
    day = days[0]
    assert "placeholder" not in day  # has an entry now
    assert len(day["entries"]) == 1
    assert day["entries"][0]["id"] == entry["id"]
    assert 0 <= day["weekday"] <= 6

    # Update
    patched = cal_client.patch(
        CAL + f"/entries/{entry['id']}", json={"title": "Beach trip"}
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Beach trip"

    # Delete
    assert cal_client.delete(CAL + f"/entries/{entry['id']}").status_code == 204
    assert cal_client.get(CAL + f"/entries/{entry['id']}").status_code == 404


def test_image_upload_and_serve(cal_client: TestClient):
    date = dt.date.today().isoformat()
    entry = cal_client.post(CAL + "/entries", json={"date": date, "title": "Pic"}).json()

    up = cal_client.post(
        CAL + f"/entries/{entry['id']}/images",
        files={"file": ("p.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert up.status_code == 201, up.text
    img = up.json()
    assert img["mime"] == "image/png"

    # The entry now reports the image; the blob streams back.
    fetched = cal_client.get(CAL + f"/entries/{entry['id']}").json()
    assert len(fetched["images"]) == 1
    h = fetched["images"][0]["hash"]
    blob = cal_client.get(CAL + f"/image/{h}")
    assert blob.status_code == 200
    assert blob.headers["content-type"] == "image/png"

    # Rejects a non-image.
    bad = cal_client.post(
        CAL + f"/entries/{entry['id']}/images",
        files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert bad.status_code == 415


def test_due_reminder_fires_notification(cal_client: TestClient):
    date = dt.date.today().isoformat()
    # A reminder already in the past → the scheduler should fire it promptly.
    cal_client.post(
        CAL + "/entries",
        json={
            "date": date,
            "title": "Call mom",
            "description": "Wish her happy birthday.",
            "remind_at": time.time() - 1,
        },
    )
    # Give the background scheduler a moment to drain.
    notified = False
    for _ in range(50):
        notes = cal_client.get("/api/notifications").json()["items"]
        if any(n["title"] == "Call mom" for n in notes):
            notified = True
            break
        time.sleep(0.1)
    assert notified, "due reminder did not produce a notification"


def test_vibe_today(cal_client: TestClient):
    data = cal_client.get(VIBE + "/today").json()
    assert data["quote"]
    assert data["font"]
    assert data["accent"].startswith("#")
    # The image endpoint serves the cached (gradient, offline) image.
    img = cal_client.get(VIBE + f"/image/{data['date']}")
    assert img.status_code == 200
    assert img.headers["content-type"] in ("image/jpeg", "image/svg+xml")
