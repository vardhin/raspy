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

    def test_priority_sets_sorts_and_cycles(self, client):
        # priority accepts a string (declarative select sends strings) and clamps.
        lo = client.post(
            "/api/att/todo/items", json={"title": "lo", "priority": "1"}
        ).json()
        hi = client.post(
            "/api/att/todo/items", json={"title": "hi", "priority": 3}
        ).json()
        assert hi["priority"] == 3
        assert hi["priority_label"] == "High"
        # higher priority sorts first among incomplete items
        order = [i["title"] for i in client.get("/api/att/todo/items").json()]
        assert order == ["hi", "lo"]
        # cycle wraps 1 -> 2 -> 3 -> 0
        for expected in (2, 3, 0):
            assert (
                client.post(f"/api/att/todo/items/{lo['id']}/cycle-priority").json()[
                    "priority"
                ]
                == expected
            )

    def test_due_date_set_and_clear(self, client):
        item = client.post(
            "/api/att/todo/items", json={"title": "d", "due": "2999-01-02"}
        ).json()
        assert item["due"] == "2999-01-02"
        assert item["due_variant"] == "info"  # far future
        assert "Due" in item["due_label"]
        # clearing removes the due date
        cleared = client.patch(
            f"/api/att/todo/items/{item['id']}", json={"clear_due": True}
        ).json()
        assert cleared["due"] is None
        assert cleared["due_label"] == ""
        # empty-string due is treated as no due date (declarative input clears to "")
        none_due = client.post(
            "/api/att/todo/items", json={"title": "e", "due": ""}
        ).json()
        assert none_due["due"] is None


class TestPomodoro:
    def test_settings_and_session_lifecycle(self, client):
        # default state: idle
        s = client.get("/api/att/pomodoro/state").json()
        assert s["running"] is False
        assert s["phase"] == "work"

        # settings round-trip + clamping handled by validation (180 cap)
        client.put(
            "/api/att/pomodoro/settings",
            json={"work_minutes": 50, "break_minutes": 10},
        )
        cfg = client.get("/api/att/pomodoro/settings").json()
        assert cfg == {"work_minutes": 50, "break_minutes": 10}

        # start a focus phase linked to a todo
        started = client.post(
            "/api/att/pomodoro/start",
            json={"phase": "work", "todo_id": 7, "todo_title": "ship it"},
        ).json()
        assert started["running"] is True
        assert started["phase"] == "work"
        assert started["todo_title"] == "ship it"
        # 50 minutes => ~3000s remaining, ends_at in the future
        assert 2990 < started["remaining"] <= 3000
        assert started["ends_at"] is not None

        # pause holds the remaining time and stops the clock
        paused = client.post("/api/att/pomodoro/pause").json()
        assert paused["running"] is False
        assert paused["ends_at"] is None
        assert paused["remaining"] > 0

        # resume restarts the countdown
        resumed = client.post("/api/att/pomodoro/resume").json()
        assert resumed["running"] is True
        assert resumed["ends_at"] is not None

        # reset clears everything back to idle
        reset = client.post("/api/att/pomodoro/reset").json()
        assert reset["running"] is False
        assert reset["todo_title"] is None
        assert reset["remaining"] == 0

    def test_invalid_phase_and_settings_bounds(self, client):
        assert (
            client.post("/api/att/pomodoro/start", json={"phase": "nap"}).status_code
            == 400
        )
        assert (
            client.put(
                "/api/att/pomodoro/settings",
                json={"work_minutes": 999, "break_minutes": 5},
            ).status_code
            == 422
        )


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


class TestUpdates:
    def test_app_is_discovered_and_admin_only(self, client):
        # The updates app loads and is mounted (router admin-gated).
        h = client.get("/api/healthz").json()
        loaded = {a["id"] for a in h["attachments"]["loaded"]}
        assert "updates" in loaded
        # The seeded `client` is the original admin, so the manifest includes it.
        ids = {a["id"] for a in client.get("/api/manifest").json()["attachments"]}
        assert "updates" in ids

    def test_autocheck_get_and_set_round_trip(self, client):
        # No network: pure local override file.
        cfg = client.get("/api/update/autocheck").json()
        assert set(cfg) == {"enabled", "interval_s"}
        # Disable
        off = client.put(
            "/api/update/autocheck", json={"enabled": False, "interval_s": 0}
        ).json()
        assert off["enabled"] is False
        assert client.get("/api/update/autocheck").json()["enabled"] is False
        # Re-enable with a custom interval
        on = client.put(
            "/api/update/autocheck", json={"enabled": True, "interval_s": 3600}
        ).json()
        assert on == {"enabled": True, "interval_s": 3600}

    def test_apply_rejects_when_not_frozen(self, client):
        # Tests don't run a frozen binary, so apply must refuse before any network.
        res = client.post("/api/update/apply", json={"target": "v0.0.1"}).json()
        assert res["ok"] is False
        assert "frozen" in res["error"] or "platform" in res["error"]

    def test_installed_tag_drives_current(self, client):
        # No network: poke the updater directly (it lives on app.state) to record
        # an installed tag, then confirm /status reports it as current_tag.
        updater = client.app.state.updater
        assert updater.installed_tag() is None
        updater._record_installed_tag("v0.4.0")
        assert updater.installed_tag() == "v0.4.0"
        st = client.get("/api/update/status").json()
        assert st["current_tag"] == "v0.4.0"

    def test_binary_cache_list_and_delete(self, client):
        from raspy.core.updater import _asset_name

        updater = client.app.state.updater
        asset = _asset_name()
        if asset is None:
            return  # unknown platform — cache keys off the asset name
        # Seed a fake cached binary for a tag and confirm it's discovered.
        cached = updater._cached_path("v0.3.0", asset)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(b"fake-binary")
        assert "v0.3.0" in updater.cached_tags()
        # Delete via the admin route reclaims it.
        r = client.delete("/api/update/cache/v0.3.0")
        assert r.json()["ok"] is True
        assert "v0.3.0" not in updater.cached_tags()
        # Deleting a non-cached tag is a clean error, not a crash.
        assert client.delete("/api/update/cache/v9.9.9").json()["ok"] is False


def test_attachment_data_isolation(client):
    # todo and notes use separately-prefixed tables; creating in one doesn't leak.
    client.post("/api/att/todo/items", json={"title": "t"})
    client.post("/api/att/notes/notes", json={"title": "n", "body": ""})
    assert len(client.get("/api/att/todo/items").json()) == 1
    assert len(client.get("/api/att/notes/notes").json()) == 1
