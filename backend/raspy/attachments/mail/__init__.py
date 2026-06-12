"""Mail attachment — Gmail inbox aggregator.

Accounts are added from the frontend with a Gmail app password. Passwords are
encrypted at rest with a local key under this attachment's data dir and are never
returned by the API. The first fetch starts at the account's creation timestamp:
existing older mail is ignored, but downtime after that point is caught up on the
next poll by Gmail UID.
"""

from __future__ import annotations

import asyncio
import email
import html
import imaplib
import json
import os
import re
import shlex
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, parseaddr
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment

_HOST = "imap.gmail.com"
_PORT = 993
_DEFAULT_POLL_SECONDS = 60
_MIN_POLL_SECONDS = 60
_BODY_BYTES = 128 * 1024
_BODY_CHARS = 40_000


class AccountCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    app_password: str = Field(min_length=8, max_length=256)
    poll_seconds: int = Field(default=_DEFAULT_POLL_SECONDS, ge=_MIN_POLL_SECONDS, le=3600)
    notify: bool = False

    @field_validator("email")
    @classmethod
    def gmail_address(cls, value: str) -> str:
        address = value.lower().strip()
        if "@" not in address or address.startswith("@") or address.endswith("@"):
            raise ValueError("valid email address required")
        return address


class AccountUpdate(BaseModel):
    poll_seconds: int | None = Field(default=None, ge=_MIN_POLL_SECONDS, le=3600)
    active: bool | None = None
    notify: bool | None = None


@dataclass
class GmailMessage:
    uid: int
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    sent_at: float
    labels: list[str]
    snippet: str
    body: str


class Mail(BaseAttachment):
    id = "mail"
    title = "Mail"
    icon = "mail"
    version = "1.0.0"

    _poller: asyncio.Task[None] | None = None
    _stop: asyncio.Event
    _wake: asyncio.Event
    _fetch_lock: asyncio.Lock
    _fernet: Fernet

    async def on_load(self, ctx: AttachmentContext) -> None:
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._fetch_lock = asyncio.Lock()
        self._fernet = Fernet(_load_or_create_key(ctx.data_dir / "mail.key"))
        await self._create_tables()
        self._poller = asyncio.create_task(self._poll_loop())

    async def on_shutdown(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._poller is not None:
            try:
                await self._poller
            except asyncio.CancelledError:
                pass
            self._poller = None

    async def _create_tables(self) -> None:
        accounts = self.db.table("accounts")
        messages = self.db.table("messages")
        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {accounts} (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                email          TEXT    NOT NULL UNIQUE,
                app_password   TEXT    NOT NULL,
                start_after    REAL    NOT NULL,
                poll_seconds   INTEGER NOT NULL DEFAULT {_DEFAULT_POLL_SECONDS},
                notify         INTEGER NOT NULL DEFAULT 0,
                active         INTEGER NOT NULL DEFAULT 1,
                last_uid       INTEGER NOT NULL DEFAULT 0,
                last_poll      REAL,
                last_ok        REAL,
                last_error     TEXT,
                created        REAL    NOT NULL,
                updated        REAL    NOT NULL
            )
            """
        )
        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {messages} (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id     INTEGER NOT NULL,
                uid            INTEGER NOT NULL,
                message_id     TEXT    NOT NULL DEFAULT '',
                subject        TEXT    NOT NULL DEFAULT '',
                sender_name    TEXT    NOT NULL DEFAULT '',
                sender_email   TEXT    NOT NULL DEFAULT '',
                sent_at        REAL    NOT NULL,
                labels         TEXT    NOT NULL DEFAULT '[]',
                snippet        TEXT    NOT NULL DEFAULT '',
                body           TEXT    NOT NULL DEFAULT '',
                fetched        REAL    NOT NULL,
                FOREIGN KEY(account_id) REFERENCES {accounts}(id) ON DELETE CASCADE,
                UNIQUE(account_id, uid)
            )
            """
        )
        await self.db.execute(
            f"CREATE INDEX IF NOT EXISTS {messages}_sent ON {messages} (sent_at DESC)"
        )
        await self.db.execute(
            f"CREATE INDEX IF NOT EXISTS {messages}_sender ON {messages} (sender_email)"
        )

    def router(self) -> APIRouter:
        r = APIRouter()
        accounts = self.db.table("accounts")
        messages = self.db.table("messages")

        @r.get("/accounts")
        async def list_accounts() -> list[dict[str, Any]]:
            rows = await self.db.fetch_all(f"SELECT * FROM {accounts} ORDER BY email")
            return [self._account_api(row) for row in rows]

        @r.post("/accounts", status_code=201)
        async def add_account(body: AccountCreate) -> dict[str, Any]:
            address = body.email.lower().strip()
            password = _clean_app_password(body.app_password)
            try:
                await asyncio.to_thread(test_gmail_login, address, password)
            except Exception as exc:  # noqa: BLE001 - surface provider error
                raise HTTPException(400, f"Gmail login failed: {exc}") from exc

            now = time.time()
            encrypted = self._encrypt(password)
            try:
                new_id = await self.db.execute_insert(
                    f"""
                    INSERT INTO {accounts}
                    (email, app_password, start_after, poll_seconds, notify, active,
                     last_uid, created, updated)
                    VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?)
                    """,
                    (
                        address,
                        encrypted,
                        now,
                        body.poll_seconds,
                        1 if body.notify else 0,
                        now,
                        now,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(409, "account already exists") from exc

            self.events.publish("mail.accounts.changed", {"id": new_id})
            self._wake.set()
            row = await self._account_row(new_id)
            return self._account_api(row)

        @r.patch("/accounts/{account_id}")
        async def update_account(account_id: int, body: AccountUpdate) -> dict[str, Any]:
            await self._account_row(account_id)
            sets: list[str] = []
            params: list[Any] = []
            if body.poll_seconds is not None:
                sets.append("poll_seconds = ?")
                params.append(body.poll_seconds)
            if body.active is not None:
                sets.append("active = ?")
                params.append(1 if body.active else 0)
            if body.notify is not None:
                sets.append("notify = ?")
                params.append(1 if body.notify else 0)
            if sets:
                sets.append("updated = ?")
                params.append(time.time())
                params.append(account_id)
                await self.db.execute(
                    f"UPDATE {accounts} SET {', '.join(sets)} WHERE id = ?", params
                )
            row = await self._account_row(account_id)
            self.events.publish("mail.accounts.changed", {"id": account_id})
            return self._account_api(row)

        @r.delete("/accounts/{account_id}", status_code=204)
        async def delete_account(account_id: int) -> None:
            await self._account_row(account_id)
            await self.db.execute(f"DELETE FROM {accounts} WHERE id = ?", (account_id,))
            self.events.publish("mail.accounts.changed", {"id": account_id})
            self.events.publish("mail.messages.changed", None)

        @r.get("/messages")
        async def list_messages(
            q: str = Query(default=""),
            sender: str = Query(default=""),
            account_id: int | None = Query(default=None),
            limit: int = Query(default=100, ge=1, le=500),
            offset: int = Query(default=0, ge=0),
        ) -> list[dict[str, Any]]:
            where = ["1 = 1"]
            params: list[Any] = []
            if q.strip():
                like = f"%{q.strip()}%"
                where.append(
                    "(m.subject LIKE ? OR m.snippet LIKE ? OR m.body LIKE ? "
                    "OR m.sender_name LIKE ? OR m.sender_email LIKE ?)"
                )
                params.extend([like, like, like, like, like])
            if sender.strip():
                like = f"%{sender.strip().lower()}%"
                where.append("LOWER(m.sender_email) LIKE ?")
                params.append(like)
            if account_id is not None:
                where.append("m.account_id = ?")
                params.append(account_id)
            # Page through the newest-first list with limit + offset. The ordering is
            # fully deterministic (sent_at, then id) so a page boundary is stable.
            params.append(limit)
            params.append(offset)
            rows = await self.db.fetch_all(
                f"""
                SELECT m.*, a.email AS account_email
                FROM {messages} m
                JOIN {accounts} a ON a.id = m.account_id
                WHERE {' AND '.join(where)}
                ORDER BY m.sent_at DESC, m.id DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            return [self._message_api(row) for row in rows]

        @r.get("/messages/{message_id}")
        async def get_message(message_id: int) -> dict[str, Any]:
            row = await self.db.fetch_one(
                f"""
                SELECT m.*, a.email AS account_email
                FROM {messages} m
                JOIN {accounts} a ON a.id = m.account_id
                WHERE m.id = ?
                """,
                (message_id,),
            )
            if row is None:
                raise HTTPException(404, "message not found")
            return self._message_api(row)

        @r.post("/fetch", status_code=202)
        async def fetch_all() -> dict[str, Any]:
            return await self.fetch_due(force=True)

        @r.post("/accounts/{account_id}/fetch", status_code=202)
        async def fetch_one(account_id: int) -> dict[str, Any]:
            return await self.fetch_account(account_id)

        return r

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Mail", children=[ui.mail_client()])

    async def _account_row(self, account_id: int) -> dict[str, Any]:
        row = await self.db.fetch_one(
            f"SELECT * FROM {self.db.table('accounts')} WHERE id = ?", (account_id,)
        )
        if row is None:
            raise HTTPException(404, "mail account not found")
        return row

    def _account_api(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "email": row["email"],
            "configured": True,
            "start_after": row["start_after"],
            "poll_seconds": row["poll_seconds"],
            "notify": bool(row["notify"]),
            "active": bool(row["active"]),
            "last_uid": row["last_uid"],
            "last_poll": row["last_poll"],
            "last_ok": row["last_ok"],
            "last_error": row["last_error"],
            "created": row["created"],
            "updated": row["updated"],
        }

    def _message_api(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "account_id": row["account_id"],
            "account_email": row["account_email"],
            "uid": row["uid"],
            "message_id": row["message_id"],
            "subject": row["subject"],
            "sender_name": row["sender_name"],
            "sender_email": row["sender_email"],
            "sent_at": row["sent_at"],
            "labels": json.loads(row["labels"] or "[]"),
            "snippet": row["snippet"],
            "body": row["body"],
            "fetched": row["fetched"],
        }

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("stored app password cannot be decrypted") from exc

    async def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.fetch_due(force=False)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - polling should not kill the app
                pass
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=15)
                self._wake.clear()
            except TimeoutError:
                pass

    async def fetch_due(self, *, force: bool) -> dict[str, Any]:
        table = self.db.table("accounts")
        now = time.time()
        if force:
            rows = await self.db.fetch_all(f"SELECT * FROM {table} WHERE active = 1")
        else:
            rows = await self.db.fetch_all(
                f"""
                SELECT * FROM {table}
                WHERE active = 1
                  AND (last_poll IS NULL OR (? - last_poll) >= poll_seconds)
                """,
                (now,),
            )
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(await self.fetch_account(int(row["id"])))
        return {"accounts": len(results), "results": results}

    async def fetch_account(self, account_id: int) -> dict[str, Any]:
        async with self._fetch_lock:
            account = await self._account_row(account_id)
            if not account["active"]:
                return {"account_id": account_id, "fetched": 0, "skipped": "inactive"}
            password = self._decrypt(account["app_password"])
            started = time.time()
            try:
                fetched = await asyncio.to_thread(fetch_gmail_messages, account, password)
                inserted = await self._store_messages(account, fetched)
                max_uid = max([account["last_uid"], *[m.uid for m in fetched]], default=0)
                await self.db.execute(
                    f"""
                    UPDATE {self.db.table('accounts')}
                    SET last_poll = ?, last_ok = ?, last_error = NULL, last_uid = ?, updated = ?
                    WHERE id = ?
                    """,
                    (started, time.time(), max_uid, time.time(), account_id),
                )
                if inserted:
                    self.events.publish("mail.messages.changed", {"account_id": account_id})
                return {"account_id": account_id, "fetched": len(fetched), "inserted": inserted}
            except Exception as exc:  # noqa: BLE001
                await self.db.execute(
                    f"""
                    UPDATE {self.db.table('accounts')}
                    SET last_poll = ?, last_error = ?, updated = ?
                    WHERE id = ?
                    """,
                    (started, str(exc), time.time(), account_id),
                )
                self.events.publish("mail.accounts.changed", {"id": account_id})
                return {"account_id": account_id, "fetched": 0, "error": str(exc)}

    async def _store_messages(
        self, account: dict[str, Any], fetched: list[GmailMessage]
    ) -> int:
        if not fetched:
            return 0
        table = self.db.table("messages")
        inserted = 0
        now = time.time()
        for msg in fetched:
            # INSERT OR IGNORE dedups on UNIQUE(account_id, uid). Use rows_affected,
            # not lastrowid, to tell a genuine insert from an ignored duplicate:
            # SQLite leaves lastrowid pointing at the prior insert when a row is
            # ignored, which would otherwise re-notify the same mail every poll.
            new_id, changed = await self.db.execute_insert_changed(
                f"""
                INSERT OR IGNORE INTO {table}
                (account_id, uid, message_id, subject, sender_name, sender_email,
                 sent_at, labels, snippet, body, fetched)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account["id"],
                    msg.uid,
                    msg.message_id,
                    msg.subject,
                    msg.sender_name,
                    msg.sender_email,
                    msg.sent_at,
                    json.dumps(msg.labels),
                    msg.snippet,
                    msg.body,
                    now,
                ),
            )
            if changed:
                inserted += 1
                if account["notify"]:
                    await self.notify(
                        f"Mail from {msg.sender_email}",
                        msg.subject or msg.snippet,
                        icon="mail",
                        url="/a/mail",
                        data={"message_id": new_id, "account_id": account["id"]},
                    )
        return inserted


def _load_or_create_key(path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return path.read_bytes()
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def _clean_app_password(value: str) -> str:
    return "".join(value.strip().split())


def test_gmail_login(address: str, password: str) -> None:
    with imaplib.IMAP4_SSL(_HOST, _PORT, timeout=30) as imap:
        status, data = imap.login(address, password)
        if status != "OK":
            raise RuntimeError(_imap_error(data) or "login rejected")


def fetch_gmail_messages(account: dict[str, Any], password: str) -> list[GmailMessage]:
    with imaplib.IMAP4_SSL(_HOST, _PORT, timeout=30) as imap:
        status, data = imap.login(account["email"], password)
        if status != "OK":
            raise RuntimeError(_imap_error(data) or "login rejected")
        status, data = imap.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError(_imap_error(data) or "could not open INBOX")

        last_uid = int(account["last_uid"] or 0)
        if last_uid > 0:
            status, data = imap.uid("search", None, "UID", f"{last_uid + 1}:*")
        else:
            status, data = imap.uid("search", None, "SINCE", _imap_date(account["start_after"]))
        if status != "OK":
            raise RuntimeError(_imap_error(data) or "search failed")

        uids = [int(raw) for raw in (data[0] or b"").split() if raw.isdigit()]
        messages: list[GmailMessage] = []
        for uid in uids:
            msg = _fetch_one(imap, uid)
            if last_uid == 0 and msg.sent_at + 60 < float(account["start_after"]):
                continue
            messages.append(msg)
        return messages


def _fetch_one(imap: imaplib.IMAP4_SSL, uid: int) -> GmailMessage:
    header_fields = (
        "MESSAGE-ID FROM SUBJECT DATE CONTENT-TYPE CONTENT-TRANSFER-ENCODING"
    )
    status, data = imap.uid(
        "fetch",
        str(uid),
        f"(UID X-GM-LABELS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({header_fields})])",
    )
    if status != "OK":
        raise RuntimeError(_imap_error(data) or f"fetch headers failed for UID {uid}")
    meta, headers = _tuple_payload(data)

    status, body_data = imap.uid("fetch", str(uid), f"(BODY.PEEK[TEXT]<0.{_BODY_BYTES}>)")
    if status != "OK":
        raise RuntimeError(_imap_error(body_data) or f"fetch body failed for UID {uid}")
    _body_meta, body = _tuple_payload(body_data)

    msg = BytesParser(policy=policy.default).parsebytes(headers + b"\r\n" + body)
    sender_name, sender_email = parseaddr(str(msg.get("From", "")))
    content = _message_text(msg)
    subject = str(msg.get("Subject", "")).strip()
    labels = _parse_labels(meta)
    sent_at = _message_timestamp(msg, meta)
    return GmailMessage(
        uid=uid,
        message_id=str(msg.get("Message-ID", "")).strip(),
        subject=subject,
        sender_name=sender_name,
        sender_email=sender_email.lower(),
        sent_at=sent_at,
        labels=labels,
        snippet=_snippet(content),
        body=content[:_BODY_CHARS],
    )


def _tuple_payload(data: list[Any]) -> tuple[bytes, bytes]:
    for item in data:
        if isinstance(item, tuple) and len(item) >= 2:
            meta = item[0] if isinstance(item[0], bytes) else bytes(item[0])
            payload = item[1] if isinstance(item[1], bytes) else bytes(item[1])
            return meta, payload
    return b"", b""


def _message_text(msg: email.message.EmailMessage) -> str:
    plain: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        parts = msg.walk()
    else:
        parts = [msg]
    for part in parts:
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or "").lower()
        if disposition == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            payload = part.get_content()
        except Exception:  # noqa: BLE001
            raw = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            payload = raw.decode(charset, errors="replace")
        if not isinstance(payload, str):
            continue
        if content_type == "text/plain":
            plain.append(payload)
        else:
            html_parts.append(_html_to_text(payload))
    text = "\n\n".join(p.strip() for p in (plain or html_parts) if p.strip())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n\n", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"[ \t]+", " ", value)


def _snippet(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:280]


def _message_timestamp(msg: email.message.EmailMessage, meta: bytes) -> float:
    date_header = str(msg.get("Date", "")).strip()
    if date_header:
        try:
            dt = parsedate_to_datetime(date_header)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.timestamp()
        except Exception:  # noqa: BLE001
            pass
    m = re.search(rb'INTERNALDATE "([^"]+)"', meta)
    if m:
        try:
            dt = parsedate_to_datetime(m.group(1).decode().replace("-", " "))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.timestamp()
        except Exception:  # noqa: BLE001
            pass
    return time.time()


def _parse_labels(meta: bytes) -> list[str]:
    m = re.search(rb"X-GM-LABELS \((.*?)\)", meta)
    if not m:
        return ["INBOX"]
    raw = m.group(1).decode(errors="replace")
    try:
        labels = shlex.split(raw)
    except ValueError:
        labels = raw.split()
    clean = [label.strip('"') for label in labels if label.strip('"')]
    return clean or ["INBOX"]


def _imap_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%d-%b-%Y")


def _imap_error(data: Any) -> str:
    if not data:
        return ""
    first = data[0] if isinstance(data, list | tuple) else data
    if isinstance(first, bytes):
        return first.decode(errors="replace")
    return str(first)


attachment = Mail()
