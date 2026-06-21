"""Passwords keeper: the server is a dumb opaque store, exactly like the vault's
manifest. These tests confirm it stores/returns the encrypted blob verbatim,
treats it as opaque, and is gated like any attachment. The actual encryption is
the client's job (libsodium under the master key) and isn't exercised here — the
point is that the Pi can't read anything."""

from __future__ import annotations


def test_empty_store_is_204(client):
    assert client.get("/api/att/passwords/store").status_code == 204


def test_store_roundtrip_opaque(client):
    # An "encrypted keeper" is just opaque bytes to the server.
    blob = b"\x00\x01\x02encrypted-passwords-bytes\xff\xfe"
    assert client.put("/api/att/passwords/store", content=blob).status_code == 204
    r = client.get("/api/att/passwords/store")
    assert r.status_code == 200
    assert r.content == blob  # byte-identical, untouched
    assert r.headers["content-type"] == "application/octet-stream"


def test_store_overwrite_replaces(client):
    client.put("/api/att/passwords/store", content=b"first")
    client.put("/api/att/passwords/store", content=b"second-version")
    assert client.get("/api/att/passwords/store").content == b"second-version"


def test_store_too_large_rejected(client):
    big = b"x" * (16 * 1024 * 1024 + 1)
    assert client.put("/api/att/passwords/store", content=big).status_code == 413
    # Nothing was stored.
    assert client.get("/api/att/passwords/store").status_code == 204


def test_store_delete(client):
    client.put("/api/att/passwords/store", content=b"blob")
    assert client.delete("/api/att/passwords/store").status_code == 204
    assert client.get("/api/att/passwords/store").status_code == 204
    # Delete is idempotent.
    assert client.delete("/api/att/passwords/store").status_code == 204


def test_passwords_requires_auth(client):
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    assert client.get("/api/att/passwords/store").status_code == 401
