"""Notifications core service: history, read-state, subscriptions, and that an
attachment's ctx.notify() lands in history + on the event bus."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from raspy.config import Settings
from raspy.core.db import Database
from raspy.core.events import EventBus
from raspy.core.notifications import NotificationService, _GoneError


def test_test_endpoint_records_notification(client: TestClient) -> None:
    res = client.post("/api/notifications/test", json={"title": "Hi", "body": "there"})
    assert res.status_code == 201
    note = res.json()
    assert note["title"] == "Hi"
    assert note["read"] is False

    listing = client.get("/api/notifications").json()
    assert listing["unread"] == 1
    assert listing["items"][0]["title"] == "Hi"


def test_mark_read_and_read_all(client: TestClient) -> None:
    a = client.post("/api/notifications/test", json={"title": "a"}).json()
    client.post("/api/notifications/test", json={"title": "b"})
    assert client.get("/api/notifications").json()["unread"] == 2

    client.post(f"/api/notifications/{a['id']}/read")
    assert client.get("/api/notifications").json()["unread"] == 1

    client.post("/api/notifications/read-all")
    assert client.get("/api/notifications").json()["unread"] == 0


def test_clear(client: TestClient) -> None:
    client.post("/api/notifications/test", json={"title": "x"})
    client.delete("/api/notifications")
    assert client.get("/api/notifications").json()["items"] == []


def test_subscribe_unsubscribe(client: TestClient) -> None:
    sub = {
        "kind": "webpush",
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": "k", "auth": "a"},
    }
    assert client.post("/api/notifications/subscribe", json=sub).status_code == 201
    # Idempotent upsert: same endpoint again is fine.
    assert client.post("/api/notifications/subscribe", json=sub).status_code == 201

    res = client.post(
        "/api/notifications/unsubscribe", json={"endpoint": sub["endpoint"]}
    )
    assert res.status_code == 204


def test_vapid_key_endpoint(client: TestClient) -> None:
    # No VAPID configured in the test Settings → key is null, endpoint still 200.
    res = client.get("/api/notifications/vapid-key")
    assert res.status_code == 200
    assert "key" in res.json()


def test_attachment_notify_lands_in_history(client: TestClient) -> None:
    # The todo attachment calls self.notify() on create (see attachments/todo).
    created = client.post("/api/att/todo/items", json={"title": "buy milk"})
    assert created.status_code == 201

    listing = client.get("/api/notifications").json()
    titles = [n["title"] for n in listing["items"]]
    assert "New todo added" in titles
    note = next(n for n in listing["items"] if n["title"] == "New todo added")
    assert note["source"] == "todo"
    assert note["body"] == "buy milk"


# --- outbox (durable delivery queue) -----------------------------------------


async def _svc(tmp_path) -> NotificationService:
    settings = Settings(data_dir=tmp_path)
    db = Database(settings.db_path)
    db.connect()
    svc = NotificationService(db=db, events=EventBus(), settings=settings)
    await svc.init()
    return svc


async def _sub(svc: NotificationService, endpoint: str = "https://push.example/x") -> None:
    from raspy.core.notifications import PushSubscribe

    await svc.add_subscription(
        PushSubscribe(kind="webpush", endpoint=endpoint, keys={"p256dh": "k", "auth": "a"})
    )


async def test_notify_enqueues_one_outbox_row_per_subscription(tmp_path, monkeypatch) -> None:
    svc = await _svc(tmp_path)
    await _sub(svc)
    # Don't actually start the worker; inspect the queue right after notify().
    await svc.notify("hi", "there")
    stats = await svc.outbox_stats()
    assert stats.get("pending") == 1


async def test_outbox_marks_sent_on_success(tmp_path, monkeypatch) -> None:
    svc = await _svc(tmp_path)
    await _sub(svc)

    sent: list[str] = []

    async def fake_send(sub, payload):
        sent.append(sub["endpoint"])

    monkeypatch.setattr(svc, "_send_webpush", fake_send)

    await svc.notify("hi", "there")
    await svc._drain_once()

    assert sent == ["https://push.example/x"]
    assert (await svc.outbox_stats()).get("sent") == 1


async def test_outbox_prunes_gone_subscription(tmp_path, monkeypatch) -> None:
    svc = await _svc(tmp_path)
    await _sub(svc)

    async def gone(sub, payload):
        raise _GoneError

    monkeypatch.setattr(svc, "_send_webpush", gone)

    await svc.notify("hi", "there")
    await svc._drain_once()

    # Row is dead and the subscription was pruned.
    assert (await svc.outbox_stats()).get("dead") == 1
    rows = await svc._db.fetch_all("SELECT * FROM core_push_subscriptions")
    assert rows == []


async def test_outbox_retries_with_backoff_then_dies(tmp_path, monkeypatch) -> None:
    svc = await _svc(tmp_path)
    await _sub(svc)

    attempts = {"n": 0}

    async def flaky(sub, payload):
        attempts["n"] += 1
        raise RuntimeError("temporary")

    monkeypatch.setattr(svc, "_send_webpush", flaky)

    await svc.notify("hi", "there")

    # First drain: one attempt, row rescheduled (still pending, attempts=1).
    await svc._drain_once()
    row = (await svc._db.fetch_all("SELECT * FROM core_push_outbox"))[0]
    assert row["attempts"] == 1
    assert row["status"] == "pending"
    assert row["next_attempt"] > 0

    # Force it due and drain until it gives up; should stop at _MAX_ATTEMPTS.
    from raspy.core.notifications import _MAX_ATTEMPTS

    for _ in range(_MAX_ATTEMPTS):
        await svc._db.execute("UPDATE core_push_outbox SET next_attempt = 0")
        await svc._drain_once()

    assert attempts["n"] == _MAX_ATTEMPTS
    assert (await svc.outbox_stats()).get("dead") == 1
