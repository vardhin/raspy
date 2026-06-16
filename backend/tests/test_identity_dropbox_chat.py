"""Cross-account messaging: identity (public-key directory), dropbox (E2E file
drops), and chat (E2E messages + media via the dropbox).

Like the vault tests, the server is a *dumb store*: sealed metadata, sealed
payloads, and ciphertext blobs are all opaque to it. These tests therefore use
placeholder bytes/strings — the point is that the spine routes a drop into the
*recipient's* isolated store, attributes the sender, isolates accounts from each
other, and keeps everything it holds unreadable. The real sealing/unsealing is the
client's job (libsodium) and is covered by the frontend.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from raspy.config import AuthSettings, Settings
from raspy.core.app import create_app

from conftest import _seed_account, _TEST_USER, _TEST_AUTH_KEY, _FAST_ARGON

# Child temp + real credentials (auth_key only; the server never sees the password).
_CHILD = "kid"
_CHILD_TEMP_KEY = "child-temp-key"
_CHILD_TEMP_PIN = "9999"
_CHILD_REAL_KEY = "child-real-key"
_CHILD_REAL_PIN = "4321"
_SALT = "PrXc0GEAlOveYCpyIegc0Q"  # 16 bytes b64url (reused; salts aren't secret)

_BLOB = bytes(range(256)) * 4  # stand-in ciphertext
_HASH = hashlib.sha256(_BLOB).hexdigest()


def _login(c: TestClient, username: str, auth_key: str, pin: str | None = None) -> str:
    body = {"username": username, "auth_key": auth_key}
    if pin:
        body["pin"] = pin
    r = c.post("/api/auth/login", json=body)
    assert r.status_code == 200, r.text
    csrf = r.json()["csrf_token"]
    c.headers.update({"X-CSRF-Token": csrf})
    return csrf


@pytest.fixture
def two_clients(tmp_path):
    """An admin client and a fully-onboarded child client, each authenticated and
    sharing one spine, so cross-account routing is exercised end to end."""
    settings = Settings(
        data_dir=tmp_path,
        auth=AuthSettings(cookie_secure=False, **_FAST_ARGON),
    )
    _seed_account(settings)
    app = create_app(settings)

    admin = TestClient(app)
    admin.__enter__()  # trigger lifespan first (wires auth + loads attachments)
    _login(admin, _TEST_USER, _TEST_AUTH_KEY)

    # Admin creates the frozen child, allowed to use dropbox + chat.
    r = admin.post(
        "/api/auth/admin/accounts",
        json={
            "username": _CHILD,
            "auth_key": _CHILD_TEMP_KEY,
            "temp_pin": _CHILD_TEMP_PIN,
            "auth_salt": _SALT,
            "master_salt": _SALT,
            "allowed_apps": ["dropbox", "chat"],
        },
    )
    assert r.status_code == 201, r.text

    # Child onboards: log in with temp creds (frozen) → complete-setup → log in fresh.
    child = TestClient(app, base_url="http://testserver")
    csrf = _login(child, _CHILD, _CHILD_TEMP_KEY, _CHILD_TEMP_PIN)
    rs = child.post(
        "/api/auth/complete-setup",
        json={"auth_key": _CHILD_REAL_KEY, "pin": _CHILD_REAL_PIN},
        headers={"X-CSRF-Token": csrf},
    )
    assert rs.status_code == 204, rs.text
    child.cookies.clear()
    _login(child, _CHILD, _CHILD_REAL_KEY, _CHILD_REAL_PIN)

    try:
        yield admin, child
    finally:
        admin.__exit__(None, None, None)


# --- identity directory ------------------------------------------------------

def test_identity_publish_and_list(two_clients):
    admin, child = two_clients
    # Each account publishes its (opaque) public key + wrapped secret.
    assert admin.put(
        "/api/att/identity/me",
        json={"public_key": "ADMIN_PK", "sk_wrapped": "ADMIN_SKW", "sk_nonce": "N1"},
    ).status_code == 204
    assert child.put(
        "/api/att/identity/me",
        json={"public_key": "CHILD_PK", "sk_wrapped": "CHILD_SKW", "sk_nonce": "N2"},
    ).status_code == 204

    # The directory lists every account's PUBLIC key only (no wrapped secrets).
    dirr = admin.get("/api/att/identity/keys").json()
    by = {e["username"]: e for e in dirr}
    assert by[_TEST_USER]["public_key"] == "ADMIN_PK"
    assert by[_CHILD]["public_key"] == "CHILD_PK"
    assert by[_TEST_USER]["role"] == "admin"
    assert by[_CHILD]["role"] == "child"
    for e in dirr:
        assert "sk_wrapped" not in e and "sk_nonce" not in e


def test_identity_me_roundtrip_and_isolation(two_clients):
    admin, child = two_clients
    admin.put(
        "/api/att/identity/me",
        json={"public_key": "ADMIN_PK", "sk_wrapped": "ADMIN_SKW", "sk_nonce": "N1"},
    )
    # /me returns MY wrapped secret...
    me = admin.get("/api/att/identity/me").json()
    assert me == {"public_key": "ADMIN_PK", "sk_wrapped": "ADMIN_SKW", "sk_nonce": "N1"}
    # ...and a fresh account with no key gets 204, never another account's secret.
    assert child.get("/api/att/identity/me").status_code == 204


def test_identity_publish_only_own_row(two_clients):
    admin, child = two_clients
    admin.put(
        "/api/att/identity/me",
        json={"public_key": "ADMIN_PK", "sk_wrapped": "ADMIN_SKW", "sk_nonce": "N1"},
    )
    child.put(
        "/api/att/identity/me",
        json={"public_key": "CHILD_PK", "sk_wrapped": "CHILD_SKW", "sk_nonce": "N2"},
    )
    # The child writing did not clobber the admin's row (keyed by principal).
    assert admin.get("/api/att/identity/me").json()["public_key"] == "ADMIN_PK"


# --- dropbox: cross-account delivery -----------------------------------------

def _drop(c: TestClient, to: str, blob: bytes, sealed_meta: str, source: str = "drop"):
    return c.post(
        "/api/att/dropbox/send",
        data={"to": to, "sealed_meta": sealed_meta, "source": source},
        files={"file": ("blob", blob, "application/octet-stream")},
    )


def test_drop_lands_in_recipient_inbox(two_clients):
    admin, child = two_clients
    # Admin drops a file to the child.
    r = _drop(admin, _CHILD, _BLOB, "SEALED_FOR_CHILD")
    assert r.status_code == 201, r.text
    assert r.json()["hash"] == _HASH

    # The child sees it in THEIR inbox, attributed to the admin; sealed meta intact.
    items = child.get("/api/att/dropbox/items").json()
    assert len(items) == 1
    it = items[0]
    assert it["from"] == _TEST_USER
    assert it["sealed_meta"] == "SEALED_FOR_CHILD"
    assert it["size"] == len(_BLOB)

    # The admin's own inbox is empty — a drop is one-directional into the recipient.
    assert admin.get("/api/att/dropbox/items").json() == []

    # The child can stream back the (opaque) ciphertext byte-for-byte.
    got = child.get(f"/api/att/dropbox/blob/{_HASH}")
    assert got.status_code == 200
    assert got.content == _BLOB


def test_dropbox_pagination(two_clients):
    admin, child = two_clients
    # Drop several distinct blobs (distinct content => distinct hashes) to the child.
    for i in range(5):
        _drop(admin, _CHILD, _BLOB + bytes([i]), f"S{i}")
    page1 = child.get("/api/att/dropbox/items?limit=2&offset=0").json()
    page2 = child.get("/api/att/dropbox/items?limit=2&offset=2").json()
    assert len(page1) == 2 and len(page2) == 2
    # Newest-first and non-overlapping pages.
    ids = [it["id"] for it in page1] + [it["id"] for it in page2]
    assert len(set(ids)) == 4
    assert ids == sorted(ids, reverse=True)


def test_drop_blob_isolated_to_recipient(two_clients):
    admin, child = two_clients
    _drop(admin, _CHILD, _BLOB, "SEALED")
    # The sender cannot read a blob it dropped into the recipient's store: it isn't
    # in the sender's own inbox/scope.
    assert admin.get(f"/api/att/dropbox/blob/{_HASH}").status_code == 404


def test_drop_to_unknown_account_404(two_clients):
    admin, _ = two_clients
    assert _drop(admin, "nobody", _BLOB, "SEALED").status_code == 404


def test_dropbox_sender_filter(two_clients):
    admin, child = two_clients
    # Two different senders drop to the child: admin and the child-to-self path is
    # not allowed, so simulate a second sender by the child dropping to the admin
    # and the admin dropping to the child.
    _drop(admin, _CHILD, _BLOB, "A1")
    _drop(admin, _CHILD, _BLOB + b"x", "A2")
    items = child.get(f"/api/att/dropbox/items?from={_TEST_USER}").json()
    assert len(items) == 2
    assert all(it["from"] == _TEST_USER for it in items)
    senders = child.get("/api/att/dropbox/senders").json()
    assert any(s["from"] == _TEST_USER and s["count"] == 2 for s in senders)


def test_drop_delete(two_clients):
    admin, child = two_clients
    _drop(admin, _CHILD, _BLOB, "SEALED")
    item_id = child.get("/api/att/dropbox/items").json()[0]["id"]
    assert child.delete(f"/api/att/dropbox/item/{item_id}").status_code == 204
    assert child.get("/api/att/dropbox/items").json() == []
    # Blob GC'd once unreferenced.
    assert child.get(f"/api/att/dropbox/blob/{_HASH}").status_code == 404


# --- chat: dual-sided E2E messages -------------------------------------------

def test_chat_message_dual_stored(two_clients):
    admin, child = two_clients
    r = admin.post(
        "/api/att/chat/send",
        json={
            "to": _CHILD,
            "kind": "text",
            "sealed_for_recipient": "FOR_CHILD",
            "sealed_for_self": "FOR_ADMIN",
        },
    )
    assert r.status_code == 201, r.text

    # The child sees the message sealed to THEM; the admin sees the copy sealed to
    # themselves. Neither sees the other's ciphertext.
    child_msgs = child.get(f"/api/att/chat/conversation?with={_TEST_USER}").json()
    assert len(child_msgs) == 1
    assert child_msgs[0]["sealed"] == "FOR_CHILD"
    assert child_msgs[0]["from"] == _TEST_USER
    assert child_msgs[0]["mine"] is False

    admin_msgs = admin.get(f"/api/att/chat/conversation?with={_CHILD}").json()
    assert len(admin_msgs) == 1
    assert admin_msgs[0]["sealed"] == "FOR_ADMIN"
    assert admin_msgs[0]["mine"] is True


def test_chat_threads_list(two_clients):
    admin, child = two_clients
    admin.post(
        "/api/att/chat/send",
        json={"to": _CHILD, "kind": "text",
              "sealed_for_recipient": "R", "sealed_for_self": "S"},
    )
    threads = child.get("/api/att/chat/threads").json()
    assert len(threads) == 1
    assert threads[0]["peer"] == _TEST_USER
    assert threads[0]["last"]["sealed"] == "R"


def test_chat_cannot_message_self(two_clients):
    admin, _ = two_clients
    r = admin.post(
        "/api/att/chat/send",
        json={"to": _TEST_USER, "kind": "text",
              "sealed_for_recipient": "x", "sealed_for_self": "x"},
    )
    assert r.status_code == 400


def test_chat_clear_is_one_sided(two_clients):
    admin, child = two_clients
    admin.post(
        "/api/att/chat/send",
        json={"to": _CHILD, "kind": "text",
              "sealed_for_recipient": "R", "sealed_for_self": "S"},
    )
    # Admin clears its own copy; the child still has theirs.
    assert admin.delete(f"/api/att/chat/conversation?with={_CHILD}").status_code == 204
    assert admin.get(f"/api/att/chat/conversation?with={_CHILD}").json() == []
    assert len(child.get(f"/api/att/chat/conversation?with={_TEST_USER}").json()) == 1


# --- auth gating -------------------------------------------------------------

def test_apps_require_auth(two_clients):
    admin, _ = two_clients
    anon = TestClient(admin.app)
    assert anon.get("/api/att/identity/keys").status_code == 401
    assert anon.get("/api/att/dropbox/items").status_code == 401
    assert anon.get("/api/att/chat/threads").status_code == 401


def test_dropbox_chat_in_child_manifest(two_clients):
    admin, child = two_clients
    ids = {a["id"] for a in child.get("/api/manifest").json()["attachments"]}
    assert {"dropbox", "chat"} <= ids
    # identity is a hidden backend service — never an app, even for the admin.
    admin_ids = {a["id"] for a in admin.get("/api/manifest").json()["attachments"]}
    assert "identity" not in admin_ids
