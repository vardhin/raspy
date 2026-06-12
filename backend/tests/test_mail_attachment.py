from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from raspy.attachments import mail as mailmod
from raspy.config import Settings
from raspy.core.app import create_app


def _client(tmp_path: Path, monkeypatch, messages: list[mailmod.GmailMessage]):
    seen: dict[str, str] = {}

    def fake_login(address: str, password: str) -> None:
        seen["login"] = address
        seen["password"] = password

    def fake_fetch(account, password: str):
        seen["fetch"] = account["email"]
        seen["password"] = password
        return messages

    monkeypatch.setattr(mailmod, "test_gmail_login", fake_login)
    monkeypatch.setattr(mailmod, "fetch_gmail_messages", fake_fetch)

    app = create_app(Settings(data_dir=tmp_path))
    return TestClient(app), seen


def test_mail_account_password_is_backend_only(tmp_path, monkeypatch):
    client, seen = _client(tmp_path, monkeypatch, [])
    with client:
        res = client.post(
            "/api/att/mail/accounts",
            json={"email": "Me@Gmail.com", "app_password": "abcd efgh ijkl mnop"},
        )
        assert res.status_code == 201
        account = res.json()
        assert account["email"] == "me@gmail.com"
        assert "app_password" not in account
        assert seen["password"] == "abcdefghijklmnop"

        listed = client.get("/api/att/mail/accounts").json()
        assert listed[0]["configured"] is True
        assert "app_password" not in listed[0]


def test_mail_manual_fetch_stores_and_searches_messages(tmp_path, monkeypatch):
    msg = mailmod.GmailMessage(
        uid=42,
        message_id="<m1@example.com>",
        subject="Quarterly planning",
        sender_name="Asha",
        sender_email="asha@example.com",
        sent_at=time.time(),
        labels=["\\Inbox", "Work"],
        snippet="Planning notes",
        body="Planning notes and launch details",
    )
    client, _seen = _client(tmp_path, monkeypatch, [msg])
    with client:
        account = client.post(
            "/api/att/mail/accounts",
            json={"email": "me@gmail.com", "app_password": "abcdefghijklmnop"},
        ).json()

        res = client.post(f"/api/att/mail/accounts/{account['id']}/fetch")
        assert res.status_code == 202

        messages = client.get("/api/att/mail/messages", params={"q": "launch"}).json()
        assert len(messages) == 1
        assert messages[0]["subject"] == "Quarterly planning"
        assert messages[0]["sender_email"] == "asha@example.com"
        assert messages[0]["account_email"] == "me@gmail.com"

        by_sender = client.get(
            "/api/att/mail/messages", params={"sender": "asha@example.com"}
        ).json()
        assert len(by_sender) == 1


def test_mail_refetch_does_not_renotify_same_message(tmp_path, monkeypatch):
    # Regression: INSERT OR IGNORE dedups duplicates, but lastrowid stays pointing
    # at the prior insert, so the old code re-notified the same mail every poll.
    msg = mailmod.GmailMessage(
        uid=99,
        message_id="<dup@example.com>",
        subject="Only notify once",
        sender_name="Asha",
        sender_email="asha@example.com",
        sent_at=time.time(),
        labels=["\\Inbox"],
        snippet="Hi",
        body="Hi there",
    )
    client, _seen = _client(tmp_path, monkeypatch, [msg])
    with client:
        account = client.post(
            "/api/att/mail/accounts",
            json={
                "email": "me@gmail.com",
                "app_password": "abcdefghijklmnop",
                "notify": True,
            },
        ).json()

        # Two fetches return the same message; only the first is a genuine insert.
        client.post(f"/api/att/mail/accounts/{account['id']}/fetch")
        client.post(f"/api/att/mail/accounts/{account['id']}/fetch")

        notes = client.get("/api/notifications").json()["items"]
        mail_notes = [n for n in notes if n["source"] == "mail"]
        assert len(mail_notes) == 1


def test_mail_delete_account_removes_cached_messages(tmp_path, monkeypatch):
    msg = mailmod.GmailMessage(
        uid=7,
        message_id="<m2@example.com>",
        subject="Hello",
        sender_name="",
        sender_email="friend@example.com",
        sent_at=time.time(),
        labels=["\\Inbox"],
        snippet="Hi",
        body="Hi there",
    )
    client, _seen = _client(tmp_path, monkeypatch, [msg])
    with client:
        account = client.post(
            "/api/att/mail/accounts",
            json={"email": "me@gmail.com", "app_password": "abcdefghijklmnop"},
        ).json()
        client.post(f"/api/att/mail/accounts/{account['id']}/fetch")
        assert client.get("/api/att/mail/messages").json()

        assert client.delete(f"/api/att/mail/accounts/{account['id']}").status_code == 204
        assert client.get("/api/att/mail/messages").json() == []


def test_mail_messages_paginate_with_limit_and_offset(tmp_path, monkeypatch):
    # 30 messages with strictly increasing sent_at, so the newest-first ordering is
    # deterministic and pages line up cleanly.
    base = time.time()
    inbox = [
        mailmod.GmailMessage(
            uid=i,
            message_id=f"<m{i}@example.com>",
            subject=f"Message {i}",
            sender_name="Sender",
            sender_email="sender@example.com",
            sent_at=base + i,
            labels=["\\Inbox"],
            snippet=f"snippet {i}",
            body=f"body {i}",
        )
        for i in range(30)
    ]
    client, _seen = _client(tmp_path, monkeypatch, inbox)
    with client:
        account = client.post(
            "/api/att/mail/accounts",
            json={"email": "me@gmail.com", "app_password": "abcdefghijklmnop"},
        ).json()
        client.post(f"/api/att/mail/accounts/{account['id']}/fetch")

        # First page of 25 — newest first (uid 29 down to 5).
        page1 = client.get(
            "/api/att/mail/messages", params={"limit": 25, "offset": 0}
        ).json()
        assert len(page1) == 25
        assert page1[0]["subject"] == "Message 29"
        assert page1[-1]["subject"] == "Message 5"

        # Second page — the remaining 5, no overlap with page 1.
        page2 = client.get(
            "/api/att/mail/messages", params={"limit": 25, "offset": 25}
        ).json()
        assert len(page2) == 5
        assert page2[0]["subject"] == "Message 4"
        assert page2[-1]["subject"] == "Message 0"

        page1_ids = {m["id"] for m in page1}
        assert page1_ids.isdisjoint({m["id"] for m in page2})

        # Past the end yields an empty page (signals "no more" to the client).
        assert client.get(
            "/api/att/mail/messages", params={"limit": 25, "offset": 30}
        ).json() == []
