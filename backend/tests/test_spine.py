"""Core spine + attachment discovery tests."""

from __future__ import annotations


def test_health_discovers_attachments(client):
    h = client.get("/api/healthz").json()
    assert h["ok"] is True
    loaded = {a["id"] for a in h["attachments"]["loaded"]}
    assert {"todo", "notes"} <= loaded
    assert h["attachments"]["errored"] == []


def test_manifest_aggregates_and_caches(client):
    r = client.get("/api/manifest")
    assert r.status_code == 200
    body = r.json()
    ids = {a["id"] for a in body["attachments"]}
    assert {"todo", "notes"} <= ids
    # every attachment carries a UI descriptor + version for client caching
    for a in body["attachments"]:
        assert a["ui"] is not None
        assert a["ui_version"]

    etag = r.headers["etag"]
    r2 = client.get("/api/manifest", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_attachments_are_namespaced_under_api_att(client):
    # routes are mounted at /api/att/<id>/...
    assert client.get("/api/att/todo/items").status_code == 200
    assert client.get("/api/att/notes/notes").status_code == 200


class TestTodo:
    def test_crud_and_toggle(self, client):
        # empty
        assert client.get("/api/att/todo/items").json() == []

        # create
        r = client.post("/api/att/todo/items", json={"title": "  buy milk  "})
        assert r.status_code == 201
        item = r.json()
        assert item["title"] == "buy milk"  # trimmed
        assert item["done"] is False
        tid = item["id"]

        # list
        assert len(client.get("/api/att/todo/items").json()) == 1

        # toggle
        assert client.post(f"/api/att/todo/items/{tid}/toggle").json()["done"] is True
        assert client.post(f"/api/att/todo/items/{tid}/toggle").json()["done"] is False

        # patch title
        r = client.patch(f"/api/att/todo/items/{tid}", json={"title": "buy oat milk"})
        assert r.json()["title"] == "buy oat milk"

        # delete
        assert client.delete(f"/api/att/todo/items/{tid}").status_code == 204
        assert client.get("/api/att/todo/items").json() == []

    def test_validation_and_404(self, client):
        assert client.post("/api/att/todo/items", json={"title": ""}).status_code == 422
        assert client.post("/api/att/todo/items/999/toggle").status_code == 404
        assert client.delete("/api/att/todo/items/999").status_code == 404

    def test_clear_done(self, client):
        a = client.post("/api/att/todo/items", json={"title": "a"}).json()
        client.post("/api/att/todo/items", json={"title": "b"})
        client.post(f"/api/att/todo/items/{a['id']}/toggle")  # mark a done
        client.post("/api/att/todo/clear-done")
        remaining = client.get("/api/att/todo/items").json()
        assert [i["title"] for i in remaining] == ["b"]

    def test_done_items_sort_last(self, client):
        a = client.post("/api/att/todo/items", json={"title": "a"}).json()
        client.post("/api/att/todo/items", json={"title": "b"})
        client.post(f"/api/att/todo/items/{a['id']}/toggle")  # a done -> last
        order = [i["title"] for i in client.get("/api/att/todo/items").json()]
        assert order == ["b", "a"]


class TestNotes:
    def test_create_list_delete(self, client):
        r = client.post(
            "/api/att/notes/notes", json={"title": "n1", "body": "hello"}
        )
        assert r.status_code == 201
        nid = r.json()["id"]
        notes = client.get("/api/att/notes/notes").json()
        assert notes[0]["title"] == "n1"
        assert client.delete(f"/api/att/notes/notes/{nid}").status_code == 204
        assert client.get("/api/att/notes/notes").json() == []


def test_attachment_data_isolation(client):
    # todo and notes use separately-prefixed tables; creating in one doesn't leak.
    client.post("/api/att/todo/items", json={"title": "t"})
    client.post("/api/att/notes/notes", json={"title": "n", "body": ""})
    assert len(client.get("/api/att/todo/items").json()) == 1
    assert len(client.get("/api/att/notes/notes").json()) == 1
