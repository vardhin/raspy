"""Notes attachment — quick persistent notes.

A second, differently-shaped app to prove the modularity: it was added by simply
dropping this package under raspy/attachments/ — no core server edits.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from raspy.core.contract import AttachmentContext, BaseAttachment
from raspy.core import ui


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=10_000)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=10_000)


class Notes(BaseAttachment):
    id = "notes"
    title = "Notes"
    icon = "file-text"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        # Per-account tables created lazily in _ensure() (name depends on the
        # requesting account, unknown at load).
        self._ready: set[str] = set()

    async def _ensure(self) -> str:
        t = self.db.table("notes")
        if t not in self._ready:
            await self.db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    title   TEXT NOT NULL,
                    body    TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL,
                    updated REAL NOT NULL
                )
                """
            )
            self._ready.add(t)
        return t

    def router(self) -> APIRouter:
        r = APIRouter()

        async def _row(note_id: int) -> dict[str, Any]:
            t = await self._ensure()
            row = await self.db.fetch_one(f"SELECT * FROM {t} WHERE id = ?", (note_id,))
            if row is None:
                raise HTTPException(404, "note not found")
            return dict(row)

        @r.get("/notes")
        async def list_notes() -> list[dict[str, Any]]:
            t = await self._ensure()
            return await self.db.fetch_all(f"SELECT * FROM {t} ORDER BY updated DESC")

        @r.post("/notes", status_code=201)
        async def create_note(body: NoteCreate) -> dict[str, Any]:
            t = await self._ensure()
            now = time.time()
            new_id = await self.db.execute_insert(
                f"INSERT INTO {t} (title, body, created, updated) VALUES (?, ?, ?, ?)",
                (body.title.strip(), body.body, now, now),
            )
            note = await _row(new_id)
            self.events.publish("notes.created", note)
            return note

        @r.patch("/notes/{note_id}")
        async def update_note(note_id: int, body: NoteUpdate) -> dict[str, Any]:
            t = await self._ensure()
            await _row(note_id)
            sets: list[str] = []
            params: list[Any] = []
            if body.title is not None:
                sets.append("title = ?")
                params.append(body.title.strip())
            if body.body is not None:
                sets.append("body = ?")
                params.append(body.body)
            if sets:
                sets.append("updated = ?")
                params.append(time.time())
                params.append(note_id)
                await self.db.execute(
                    f"UPDATE {t} SET {', '.join(sets)} WHERE id = ?", params
                )
            note = await _row(note_id)
            self.events.publish("notes.updated", note)
            return note

        @r.delete("/notes/{note_id}", status_code=204)
        async def delete_note(note_id: int) -> None:
            t = await self._ensure()
            await _row(note_id)
            await self.db.execute(f"DELETE FROM {t} WHERE id = ?", (note_id,))
            self.events.publish("notes.deleted", {"id": note_id})

        return r

    def ui(self) -> dict[str, Any]:
        # One dedicated Tier-1 node: the shell ships the full notes experience
        # (list + code-editor-style editor with markdown preview). The REST
        # endpoints above are the whole contract.
        return ui.notes(title="Notes")


attachment = Notes()
