"""Todo attachment — persistent task list with live updates.

Demonstrates the full contract: namespaced storage, CRUD API, declarative UI, and
WebSocket events so a change on one device shows up live on another.
See plan/60-roadmap.md Milestone 1.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from raspy.core.contract import AttachmentContext, BaseAttachment
from raspy.core import ui


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    done: bool | None = None


class Todo(BaseAttachment):
    id = "todo"
    title = "Todo"
    icon = "check-square"
    version = "1.0.0"

    # --- lifecycle ----------------------------------------------------------

    async def on_load(self, ctx: AttachmentContext) -> None:
        t = self.db.table("items")
        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {t} (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                title     TEXT    NOT NULL,
                done      INTEGER NOT NULL DEFAULT 0,
                position  INTEGER NOT NULL DEFAULT 0,
                created   REAL    NOT NULL,
                updated   REAL    NOT NULL
            )
            """
        )

    # --- API ----------------------------------------------------------------

    def router(self) -> APIRouter:
        r = APIRouter()
        t = self.db.table("items")

        async def _row(item_id: int) -> dict[str, Any]:
            row = await self.db.fetch_one(f"SELECT * FROM {t} WHERE id = ?", (item_id,))
            if row is None:
                raise HTTPException(404, "todo not found")
            return _to_api(row)

        @r.get("/items")
        async def list_items() -> list[dict[str, Any]]:
            rows = await self.db.fetch_all(
                f"SELECT * FROM {t} ORDER BY done ASC, position ASC, id ASC"
            )
            return [_to_api(row) for row in rows]

        @r.post("/items", status_code=201)
        async def create_item(body: TodoCreate) -> dict[str, Any]:
            now = time.time()
            max_pos = await self.db.fetch_one(
                f"SELECT COALESCE(MAX(position), 0) AS m FROM {t}"
            )
            pos = int((max_pos or {}).get("m", 0)) + 1
            new_id = await self.db.execute_insert(
                f"INSERT INTO {t} (title, done, position, created, updated) "
                f"VALUES (?, 0, ?, ?, ?)",
                (body.title.strip(), pos, now, now),
            )
            item = await _row(new_id)
            self.events.publish("todo.created", item)
            # Demo of the core notification service: any attachment can do this.
            await self.notify(
                "New todo added", item["title"], icon="check-square", url="/a/todo"
            )
            return item

        @r.patch("/items/{item_id}")
        async def update_item(item_id: int, body: TodoUpdate) -> dict[str, Any]:
            await _row(item_id)  # 404 if missing
            sets: list[str] = []
            params: list[Any] = []
            if body.title is not None:
                sets.append("title = ?")
                params.append(body.title.strip())
            if body.done is not None:
                sets.append("done = ?")
                params.append(1 if body.done else 0)
            if sets:
                sets.append("updated = ?")
                params.append(time.time())
                params.append(item_id)
                await self.db.execute(
                    f"UPDATE {t} SET {', '.join(sets)} WHERE id = ?", params
                )
            item = await _row(item_id)
            self.events.publish("todo.updated", item)
            return item

        @r.post("/items/{item_id}/toggle")
        async def toggle_item(item_id: int) -> dict[str, Any]:
            row = await _row(item_id)
            await self.db.execute(
                f"UPDATE {t} SET done = ?, updated = ? WHERE id = ?",
                (0 if row["done"] else 1, time.time(), item_id),
            )
            item = await _row(item_id)
            self.events.publish("todo.updated", item)
            return item

        @r.delete("/items/{item_id}", status_code=204)
        async def delete_item(item_id: int) -> None:
            await _row(item_id)
            await self.db.execute(f"DELETE FROM {t} WHERE id = ?", (item_id,))
            self.events.publish("todo.deleted", {"id": item_id})

        @r.post("/clear-done", status_code=204)
        async def clear_done() -> None:
            await self.db.execute(f"DELETE FROM {t} WHERE done = 1")
            self.events.publish("todo.cleared", None)

        return r

    # --- UI -----------------------------------------------------------------

    def ui(self) -> dict[str, Any]:
        return ui.view(
            title="Todo",
            children=[
                ui.surface(
                    level=2,
                    children=[
                        ui.row(
                            align="end",
                            children=[
                                ui.input(
                                    "title",
                                    label="New item",
                                    placeholder="What needs doing?",
                                ),
                                ui.button(
                                    "Add",
                                    action=ui.post("items", body={"title": "$title"}),
                                ),
                            ],
                        )
                    ],
                ),
                ui.list_(
                    source="items",
                    key="id",
                    empty="Nothing yet — add your first task.",
                    item=ui.surface(
                        interactive=True,
                        children=[
                            ui.row(
                                justify="between",
                                align="center",
                                children=[
                                    ui.row(
                                        align="center",
                                        children=[
                                            ui.checkbox(
                                                bind="done",
                                                action=ui.post("items/{id}/toggle"),
                                            ),
                                            ui.text("", bind="title", role="body"),
                                        ],
                                    ),
                                    ui.button(
                                        "Delete",
                                        variant="danger",
                                        action=ui.delete("items/{id}"),
                                    ),
                                ],
                            )
                        ],
                    ),
                ),
                ui.button(
                    "Clear completed",
                    variant="ghost",
                    action=ui.post("clear-done"),
                ),
            ],
        )


def _to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "done": bool(row["done"]),
        "position": row["position"],
        "created": row["created"],
        "updated": row["updated"],
    }


attachment = Todo()
