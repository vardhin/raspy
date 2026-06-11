"""Notifications attachment — the UI for the core notification service.

Notifications are a *core* service (history, push subscriptions, the outbox live
in raspy/core/notifications.py and are used by every attachment). This attachment
is purely the **app UI** for it: it appears in the Apps list at /a/notifications
and renders via the declarative schema, like todo.

Its router is a thin delegate over the core service (reached through
``self.ctx.notifications``) — no duplicate storage. The browser-only bits
(Notification permission, Web Push subscribe) stay client-side in the shell;
everything server-backed (list, mark-read, delete, clear, send-test) lives here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment


class DelayBody(BaseModel):
    delay: int = Field(default=5, ge=1, le=300)


class Notifications(BaseAttachment):
    id = "notifications"
    title = "Notifications"
    icon = "bell"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        # No tables of our own — the core service owns storage. We just need it
        # to exist; if it doesn't, the router endpoints 503 below.
        pass

    # --- API (delegates to the core service) --------------------------------

    def router(self) -> APIRouter:
        r = APIRouter()

        def svc():
            s = self.ctx.notifications
            if s is None:
                raise HTTPException(503, "notification service unavailable")
            return s

        @r.get("/items")
        async def items() -> list[dict[str, Any]]:
            # List source for the declarative `list` node — must be a JSON array.
            # Add a relative-time-friendly `when` and a read badge label per row.
            notes = await svc().list(limit=100)
            for n in notes:
                n["badge"] = "" if n["read"] else "NEW"
            return notes

        @r.post("/items/{note_id}/read", status_code=204)
        async def mark_read(note_id: int) -> None:
            await svc().mark_read(note_id)
            self._touch()

        @r.post("/read-all", status_code=204)
        async def read_all() -> None:
            await svc().mark_all_read()
            self._touch()

        @r.delete("/items/{note_id}", status_code=204)
        async def delete_one(note_id: int) -> None:
            # The core service has no single-delete yet; mark read is the closest
            # per-row action. Real delete is added on the service below.
            await svc().delete(note_id)
            self._touch()

        @r.post("/clear", status_code=204)
        async def clear() -> None:
            await svc().clear()
            self._touch()

        @r.post("/test", status_code=201)
        async def test() -> dict[str, Any]:
            return await svc().notify(
                "Test notification",
                "Hello from your Pi 👋",
                source="notifications",
            )

        @r.post("/test-delayed", status_code=202)
        async def test_delayed(body: DelayBody | None = None) -> dict[str, Any]:
            """Fire a test notification after ``delay`` seconds, so you can
            background the tab/app and watch the *background* push arrive."""
            delay = max(1, min((body.delay if body else 5), 300))
            svc().notify_later(
                float(delay),
                f"Delayed test (+{delay}s)",
                "If you backgrounded the app, this came via Web Push 🛰️",
                source="notifications",
            )
            return {"scheduled_in": delay}

        return r

    def _touch(self) -> None:
        """Nudge open notification views to re-pull. The render context refreshes
        a view's data sources on any event topic starting with the app id."""
        self.events.publish("notifications.changed", None)

    # --- UI -----------------------------------------------------------------

    def ui(self) -> dict[str, Any]:
        return ui.view(
            title="Notifications",
            children=[
                ui.surface(
                    level=2,
                    children=[
                        ui.stack(
                            gap=3,
                            children=[
                                ui.row(
                                    justify="between",
                                    align="center",
                                    children=[
                                        ui.text(
                                            "All notifications from your Pi and its apps.",
                                            role="muted",
                                        ),
                                        ui.row(
                                            gap=2,
                                            children=[
                                                ui.button(
                                                    "Mark all read",
                                                    variant="ghost",
                                                    action=ui.post("read-all"),
                                                ),
                                                ui.button(
                                                    "Clear all",
                                                    variant="danger",
                                                    action=ui.post("clear"),
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                ui.divider(),
                                ui.text("Test delivery", role="label"),
                                ui.text(
                                    "Send now appears instantly. Delayed buttons fire after "
                                    "the countdown — background the app first to see how a "
                                    "real push notification arrives when no tab is focused.",
                                    role="muted",
                                ),
                                ui.row(
                                    gap=2,
                                    wrap=True,
                                    children=[
                                        ui.button(
                                            "Send now",
                                            variant="accent",
                                            action=ui.post("test"),
                                        ),
                                        ui.button(
                                            "In 5s",
                                            variant="neutral",
                                            action=ui.post("test-delayed", body={"delay": 5}),
                                        ),
                                        ui.button(
                                            "In 15s",
                                            variant="neutral",
                                            action=ui.post("test-delayed", body={"delay": 15}),
                                        ),
                                        ui.button(
                                            "In 30s",
                                            variant="neutral",
                                            action=ui.post("test-delayed", body={"delay": 30}),
                                        ),
                                    ],
                                ),
                            ],
                        )
                    ],
                ),
                ui.list_(
                    source="items",
                    key="id",
                    empty="No notifications yet.",
                    item=ui.surface(
                        interactive=True,
                        children=[
                            ui.row(
                                justify="between",
                                align="center",
                                children=[
                                    ui.stack(
                                        gap=1,
                                        children=[
                                            ui.row(
                                                gap=2,
                                                align="center",
                                                children=[
                                                    ui.badge(
                                                        "",
                                                        bind="badge",
                                                        variant="accent",
                                                    ),
                                                    ui.text("", bind="title", role="title"),
                                                ],
                                            ),
                                            ui.text("", bind="body", role="muted"),
                                            ui.text("", bind="source", role="label"),
                                        ],
                                    ),
                                    ui.row(
                                        gap=2,
                                        children=[
                                            ui.button(
                                                "Read",
                                                variant="ghost",
                                                action=ui.post("items/{id}/read"),
                                            ),
                                            ui.button(
                                                "Delete",
                                                variant="danger",
                                                action=ui.delete("items/{id}"),
                                            ),
                                        ],
                                    ),
                                ],
                            )
                        ],
                    ),
                ),
            ],
        )


attachment = Notifications()
