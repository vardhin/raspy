"""Vault (Layer 2): the server is a dumb opaque store. These tests confirm it
stores/returns ciphertext verbatim, content-addresses by SHA-256 with hash
verification, never inspects content, and keeps the manifest opaque. The actual
encryption is the client's job (libsodium) and isn't exercised here — the point
is that the Pi can't read anything."""

from __future__ import annotations

import hashlib

# These bytes stand in for client ciphertext; the server must treat them as opaque.
_BLOB = bytes(range(256)) * 8  # 2 KiB of arbitrary bytes
_HASH = hashlib.sha256(_BLOB).hexdigest()


def test_empty_manifest_is_204(client):
    assert client.get("/api/att/vault/manifest").status_code == 204


def test_manifest_roundtrip_opaque(client):
    # An "encrypted manifest" is just opaque bytes to the server.
    blob = b"\x00\x01\x02encrypted-manifest-bytes\xff"
    assert client.put("/api/att/vault/manifest", content=blob).status_code == 204
    r = client.get("/api/att/vault/manifest")
    assert r.status_code == 200
    assert r.content == blob  # byte-identical, untouched


def test_blob_put_get_roundtrip(client):
    r = client.put(f"/api/att/vault/blob/{_HASH}", content=_BLOB)
    assert r.status_code == 201, r.text
    assert r.json() == {"hash": _HASH, "size": len(_BLOB)}
    got = client.get(f"/api/att/vault/blob/{_HASH}")
    assert got.status_code == 200
    assert got.content == _BLOB  # returned verbatim


def test_blob_hash_mismatch_rejected(client):
    # Upload under the WRONG hash → server recomputes SHA-256 and rejects.
    wrong = "0" * 64
    r = client.put(f"/api/att/vault/blob/{wrong}", content=_BLOB)
    assert r.status_code == 400
    # And nothing was stored under that name.
    assert client.get(f"/api/att/vault/blob/{wrong}").status_code == 404


def test_invalid_hash_format_rejected(client):
    assert client.put("/api/att/vault/blob/not-a-hash", content=b"x").status_code == 400
    assert client.get("/api/att/vault/blob/short").status_code == 400


def test_blob_listing_has_no_content(client):
    client.put(f"/api/att/vault/blob/{_HASH}", content=_BLOB)
    rows = client.get("/api/att/vault/blobs").json()
    assert any(row["hash"] == _HASH and row["size"] == len(_BLOB) for row in rows)
    # The listing exposes hash + size + created only — no names, no bytes.
    for row in rows:
        assert set(row.keys()) == {"hash", "size", "created"}


def test_blob_delete(client):
    client.put(f"/api/att/vault/blob/{_HASH}", content=_BLOB)
    assert client.delete(f"/api/att/vault/blob/{_HASH}").status_code == 204
    assert client.get(f"/api/att/vault/blob/{_HASH}").status_code == 404


def test_vault_requires_auth(client):
    # Vault is under /api/att/vault — protected by the gate like any attachment.
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    assert client.get("/api/att/vault/manifest").status_code == 401
