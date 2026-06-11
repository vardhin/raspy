"""Files attachment — browse, upload, download and manage the Pi's home dir.

A Dolphin/Thunar-style file manager, confined to the operator's home directory
(``~``) by :class:`~.safety.Confinement` (no ``..`` / symlink escape, never root).

Follows the attachment contract (plan/20): namespaced API under
``/api/att/files/…``, a declarative Tier-1 UI descriptor (plan/20 §4, using the
generic file-manager nodes added to ``raspy.core.ui``), and live ``files.*``
events so a change shows up on every connected client (plan/20 §6).

Capabilities (plan/20 §7): reads and writes files within the configured root only.
The root is overridable via ``[attachments.files] root = "..."`` in config.toml.
"""

from __future__ import annotations

import os
import shutil
import stat as stat_mod
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment

from .safety import Confinement

# Inline preview caps: only small text and images are streamed for preview.
_PREVIEW_TEXT_MAX = 256 * 1024  # 256 KiB
_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonc",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".sh", ".bash",
    ".zsh", ".py", ".js", ".ts", ".tsx", ".jsx", ".svelte", ".html", ".htm",
    ".css", ".scss", ".xml", ".sql", ".c", ".h", ".cpp", ".hpp", ".rs", ".go",
    ".java", ".kt", ".rb", ".php", ".lua", ".vim", ".gitignore", ".dockerignore",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico", ".avif"}


class MkdirBody(BaseModel):
    path: str = Field(default="", description="parent dir, relative to root")
    name: str = Field(min_length=1, max_length=255)


class RenameBody(BaseModel):
    path: str = Field(min_length=1, description="entry to rename, relative to root")
    name: str = Field(min_length=1, max_length=255, description="new base name")


class MoveBody(BaseModel):
    src: str = Field(min_length=1, description="source path, relative to root")
    dest_dir: str = Field(default="", description="destination directory, relative to root")


class Files(BaseAttachment):
    id = "files"
    title = "Files"
    icon = "folder"
    version = "1.0.0"

    confine: Confinement

    async def on_load(self, ctx: AttachmentContext) -> None:
        # Root: config override, else the operator's home directory. Expanded and
        # validated once; all later access is confined under it.
        configured = ctx.config.get("root")
        root = Path(configured).expanduser() if configured else Path.home()
        if not root.is_dir():
            raise RuntimeError(f"files root is not a directory: {root}")
        self.confine = Confinement(root)

    # --- helpers ------------------------------------------------------------

    def _entry(self, abs_path: Path) -> dict[str, Any]:
        """One directory entry as a JSON-safe dict (no exceptions on bad stat)."""
        rel = self.confine.to_rel(abs_path)
        try:
            st = abs_path.lstat()
        except OSError:
            return {"name": abs_path.name, "path": rel, "kind": "other", "size": 0,
                    "modified": 0, "symlink": False}
        is_link = stat_mod.S_ISLNK(st.st_mode)
        # For symlinks, classify by the target (if it resolves safely).
        if abs_path.is_dir():
            kind = "dir"
        elif abs_path.is_file():
            kind = "file"
        else:
            kind = "other"
        return {
            "name": abs_path.name,
            "path": rel,
            "kind": kind,
            "size": st.st_size,
            "modified": st.st_mtime,
            "symlink": is_link,
        }

    @staticmethod
    def _preview_kind(p: Path) -> str:
        ext = p.suffix.lower()
        if ext in _IMAGE_EXTS:
            return "image"
        if ext in _TEXT_EXTS or p.name.lower() in {"dockerfile", "makefile", "readme"}:
            return "text"
        return "none"

    # --- API ----------------------------------------------------------------

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/list")
        async def list_dir(path: str = Query(default="")) -> dict[str, Any]:
            target = self.confine.resolve(path, must_exist=True)
            if not target.is_dir():
                raise HTTPException(400, "not a directory")
            entries: list[dict[str, Any]] = []
            try:
                with os.scandir(target) as it:
                    for de in it:
                        entries.append(self._entry(Path(de.path)))
            except PermissionError:
                raise HTTPException(403, "permission denied")
            # Dirs first, then files, each alphabetical (case-insensitive).
            entries.sort(key=lambda e: (e["kind"] != "dir", e["name"].lower()))
            rel = self.confine.to_rel(target)
            return {
                "path": rel,
                "name": target.name if rel else "~",
                "segments": _segments(rel),
                "entries": entries,
            }

        @r.get("/stat")
        async def stat_entry(path: str = Query(...)) -> dict[str, Any]:
            target = self.confine.resolve(path, must_exist=True)
            entry = self._entry(target)
            entry["preview"] = self._preview_kind(target) if target.is_file() else "none"
            return entry

        @r.get("/download")
        async def download(path: str = Query(...)) -> FileResponse:
            target = self.confine.resolve(path, must_exist=True)
            if not target.is_file():
                raise HTTPException(400, "not a file")
            return FileResponse(
                target, filename=target.name, media_type="application/octet-stream"
            )

        @r.get("/preview")
        async def preview(path: str = Query(...)) -> Response:
            target = self.confine.resolve(path, must_exist=True)
            if not target.is_file():
                raise HTTPException(400, "not a file")
            kind = self._preview_kind(target)
            if kind == "image":
                return FileResponse(target)
            if kind == "text":
                if target.stat().st_size > _PREVIEW_TEXT_MAX:
                    raise HTTPException(413, "file too large to preview")
                try:
                    text = target.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    raise HTTPException(415, "not previewable as text")
                return PlainTextResponse(text)
            raise HTTPException(415, "no preview available")

        @r.post("/upload", status_code=201)
        async def upload(
            path: str = Query(default=""), file: UploadFile = ...,  # noqa: B008
        ) -> dict[str, Any]:
            dest_dir = self.confine.resolve(path, must_exist=True)
            if not dest_dir.is_dir():
                raise HTTPException(400, "destination is not a directory")
            name = os.path.basename(file.filename or "upload.bin")
            if not name or name in {".", ".."}:
                raise HTTPException(400, "invalid filename")
            # Re-confine the final path (defends against a crafted filename).
            target = self.confine.resolve(
                (self.confine.to_rel(dest_dir) + "/" + name).lstrip("/")
            )
            try:
                with target.open("wb") as out:
                    while chunk := await file.read(1024 * 1024):
                        out.write(chunk)
            finally:
                await file.close()
            entry = self._entry(target)
            self.events.publish("files.changed", {"dir": self.confine.to_rel(dest_dir)})
            return entry

        @r.post("/mkdir", status_code=201)
        async def mkdir(body: MkdirBody) -> dict[str, Any]:
            parent = self.confine.resolve(body.path, must_exist=True)
            if not parent.is_dir():
                raise HTTPException(400, "parent is not a directory")
            name = os.path.basename(body.name)
            if not name or name in {".", ".."}:
                raise HTTPException(400, "invalid folder name")
            target = self.confine.resolve(
                (self.confine.to_rel(parent) + "/" + name).lstrip("/")
            )
            if target.exists():
                raise HTTPException(409, "already exists")
            target.mkdir()
            self.events.publish("files.changed", {"dir": body.path})
            return self._entry(target)

        @r.post("/rename")
        async def rename(body: RenameBody) -> dict[str, Any]:
            src = self.confine.resolve(body.path, must_exist=True)
            name = os.path.basename(body.name)
            if not name or name in {".", ".."}:
                raise HTTPException(400, "invalid name")
            dest = self.confine.resolve(
                (self.confine.to_rel(src.parent) + "/" + name).lstrip("/")
            )
            if dest.exists():
                raise HTTPException(409, "target already exists")
            src.rename(dest)
            self.events.publish("files.changed", {"dir": self.confine.to_rel(src.parent)})
            return self._entry(dest)

        @r.post("/move")
        async def move(body: MoveBody) -> dict[str, Any]:
            src = self.confine.resolve(body.src, must_exist=True)
            dest_dir = self.confine.resolve(body.dest_dir, must_exist=True)
            if not dest_dir.is_dir():
                raise HTTPException(400, "destination is not a directory")
            dest = self.confine.resolve(
                (self.confine.to_rel(dest_dir) + "/" + src.name).lstrip("/")
            )
            if dest == src:
                raise HTTPException(400, "source and destination are the same")
            if dest.exists():
                raise HTTPException(409, "target already exists")
            shutil.move(str(src), str(dest))
            self.events.publish("files.changed", {"dir": self.confine.to_rel(dest_dir)})
            return self._entry(dest)

        @r.delete("/delete", status_code=204)
        async def delete(path: str = Query(...)) -> None:
            target = self.confine.resolve(path, must_exist=True)
            if target == self.confine.root:
                raise HTTPException(400, "refusing to delete the root")
            parent_rel = self.confine.to_rel(target.parent)
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
            self.events.publish("files.changed", {"dir": parent_rel})

        return r

    def ui(self) -> dict[str, Any]:
        return ui.file_manager(
            list_source="list",
            title="Files",
        )


def _segments(rel: str) -> list[dict[str, str]]:
    """Breadcrumb segments for a relative path, each with a cumulative path."""
    out = [{"name": "~", "path": ""}]
    acc = ""
    for part in [p for p in rel.split("/") if p]:
        acc = f"{acc}/{part}".lstrip("/")
        out.append({"name": part, "path": acc})
    return out


attachment = Files()
