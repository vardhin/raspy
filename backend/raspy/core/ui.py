"""Declarative UI descriptor builders. See plan/20-attachments.md §"UI delivery"
and plan/45-theming.md §6.

Attachments describe their UI as a tree of plain dicts using this small, fixed
vocabulary. The frontend shell maps each node ``type`` to a themed, token-only
Svelte component and renders it — so the backend ships UI structure + wiring, the
frontend never hardcodes an attachment.

These helpers are sugar: every function returns a plain ``dict`` (a ``UINode``),
so a UI spec is just JSON. Data and actions reference the attachment's own
namespaced API via *relative* paths (e.g. ``"items"`` -> ``/api/att/<id>/items``);
the shell prefixes them.
"""

from __future__ import annotations

from typing import Any

UINode = dict[str, Any]


def _node(type_: str, **props: Any) -> UINode:
    return {"type": type_, **{k: v for k, v in props.items() if v is not None}}


# --- containers / layout ----------------------------------------------------


def view(children: list[UINode], *, title: str | None = None) -> UINode:
    return _node("view", title=title, children=children)


def stack(
    children: list[UINode],
    *,
    direction: str = "column",
    gap: int = 3,
    align: str | None = None,
    justify: str | None = None,
    wrap: bool | None = None,
) -> UINode:
    return _node(
        "stack",
        direction=direction,
        gap=gap,
        align=align,
        justify=justify,
        wrap=wrap,
        children=children,
    )


def row(children: list[UINode], *, gap: int = 2, **kw: Any) -> UINode:
    return stack(children, direction="row", gap=gap, **kw)


def surface(children: list[UINode], *, level: int = 1, interactive: bool = False) -> UINode:
    return _node("surface", level=level, interactive=interactive, children=children)


# --- content ----------------------------------------------------------------


def header(text: str) -> UINode:
    return _node("header", text=text)


def text(value: str, *, role: str = "body", bind: str | None = None) -> UINode:
    # `bind` reads a field from the surrounding data item (in a list/table row).
    return _node("text", text=value, role=role, bind=bind)


def badge(
    value: str,
    *,
    variant: str = "neutral",
    bind: str | None = None,
    variant_bind: str | None = None,
    hide_when_empty: bool = False,
) -> UINode:
    """A status pill. ``bind`` reads its text from a row field; ``variant_bind``
    reads its themed variant (neutral/accent/success/warn/danger/info) from a row
    field, so each row can color its own badge. ``hide_when_empty`` drops the badge
    entirely when its bound text is empty (e.g. a "none" priority)."""
    return _node(
        "badge",
        text=value,
        variant=variant,
        bind=bind,
        variant_bind=variant_bind,
        hide_when_empty=hide_when_empty or None,
    )


def divider() -> UINode:
    return _node("divider")


# --- inputs / actions -------------------------------------------------------


def input(
    name: str,
    *,
    placeholder: str | None = None,
    label: str | None = None,
    kind: str = "text",
) -> UINode:
    return _node("input", name=name, placeholder=placeholder, label=label, kind=kind)


def checkbox(*, bind: str, action: dict[str, Any] | None = None) -> UINode:
    return _node("checkbox", bind=bind, action=action)


def button(
    label: str,
    *,
    action: dict[str, Any],
    variant: str = "accent",
    bind: str | None = None,
    variant_bind: str | None = None,
    empty_label: str | None = None,
    size: str | None = None,
) -> UINode:
    """A button. In a list row, ``bind`` makes the label read a row field and
    ``variant_bind`` makes the themed variant read a row field, so a per-row
    control (e.g. a priority chip you click to cycle) styles itself from data.
    ``empty_label`` is shown when the bound label is empty."""
    return _node(
        "button",
        text=label,
        action=action,
        variant=variant,
        bind=bind,
        variant_bind=variant_bind,
        empty_label=empty_label,
        size=size,
    )


def select(name: str, options: list[dict[str, str]], *, label: str | None = None) -> UINode:
    return _node("select", name=name, options=options, label=label)


# --- data-bound collections -------------------------------------------------


def list_(
    *,
    source: str,
    item: UINode,
    key: str = "id",
    empty: str | None = None,
) -> UINode:
    """A list whose rows come from ``GET /api/att/<id>/<source>``.

    ``item`` is a template UINode rendered per row; its ``bind`` props read fields
    from each row object. ``{id}`` in nested actions is substituted per row.
    """
    return _node("list", source=source, item=item, key=key, empty=empty)


def table(*, source: str, columns: list[dict[str, str]], key: str = "id") -> UINode:
    return _node("table", source=source, columns=columns, key=key)


# --- file manager -----------------------------------------------------------


def file_manager(
    *,
    list_source: str = "list",
    title: str | None = None,
) -> UINode:
    """A directory browser bound to an attachment's file API.

    One composite Tier-1 node (vs. many narrow ones) so the shell's vocabulary
    grows minimally. The frontend file-manager component reads a directory via
    ``GET /api/att/<id>/<list_source>?path=<rel>`` (returning
    ``{path, name, segments, entries:[{name,path,kind,size,modified,symlink}]}``)
    and uses the attachment's conventional sibling endpoints relative to it:
    ``download``, ``preview``, ``upload``, ``mkdir``, ``rename``, ``move``,
    ``delete``. All paths are root-relative; confinement is the backend's job.
    Flutter-portable: it's pure data + wiring, no shipped client code.
    """
    return _node("file_manager", title=title, list_source=list_source)


def system_stats(*, source: str = "snapshot", title: str | None = None) -> UINode:
    """A live system-health dashboard bound to an attachment's telemetry API.

    The shell's component fetches an initial reading from
    ``GET /api/att/<id>/<source>`` and then updates live from ``stats.tick``
    WebSocket events carrying the same snapshot shape (temp, voltage, throttle,
    cpu, memory, storage, uptime). One composite Tier-1 node, Flutter-portable —
    pure data + wiring, no shipped client code.
    """
    return _node("system_stats", title=title, source=source)


def mail_client(*, title: str | None = None) -> UINode:
    """A Gmail-focused mail aggregator UI bound to the mail attachment API.

    The backend attachment owns account credentials, IMAP polling, search, and
    stored message content. The shell renders this composite node with generic
    themed controls so the app stays manifest-driven rather than hardcoded as a
    route.
    """
    return _node("mail_client", title=title)


def vibe(*, title: str | None = None) -> UINode:
    """The "Vibe of the Day" UI — one magical daily image + quote.

    The backend fetches a fresh image + quote per day from keyless public providers
    and caches them to disk (offline-resilient, stable per day), plus a random
    Google display font cached locally. The shell component reads
    ``GET /api/att/vibe/today`` (``{image_url, accent, quote, author, font}``),
    renders a sparkly star field tinted by ``accent``, loads ``font`` via
    ``/api/att/vibe/font.css``, and shows the quote. A "Fetch now" button POSTs
    ``/api/att/vibe/refresh``. One composite Tier-1 node, no shipped client code.
    """
    return _node("vibe", title=title)


def calendar(*, title: str | None = None) -> UINode:
    """A continuous-timeline calendar: memory journal + planner in one grid.

    Every day in the viewed range is a card; days with entries show photos + text,
    empty days show that day's shared "vibe" placeholder (image + quote). The shell
    component reads ``GET /api/att/calendar/range?from=&to=``, supports a zoom
    slider (cards-per-row), a week/month/custom range switch, per-day weekday tint,
    an inline photo carousel, multiple entries per day, and future entries with a
    durable ``remind_at`` notification. One composite Tier-1 node, no shipped client
    code (Flutter-portable: pure data + wiring).
    """
    return _node("calendar", title=title)


def vault(*, title: str | None = None) -> UINode:
    """The zero-knowledge vault UI (Layer 2). The backend is a *dumb* store: it
    holds opaque encrypted blobs (content-addressed by SHA-256) and one opaque
    encrypted manifest. ALL encryption/decryption happens in the shell with the
    vault master key (derived from the password, never sent to the Pi). The shell
    component fetches + decrypts the manifest to render the file list, then
    streams + decrypts individual blobs on demand for preview. Flutter-portable:
    the contract is just opaque-blob storage + an encrypted manifest.
    """
    return _node("vault", title=title)


def contacts(*, title: str | None = None) -> UINode:
    """The contacts UI — a personal address book + a "keep in touch" reminder list.

    The backend stores each contact's plaintext fields (name, description, phone,
    email, address) plus any number of end-to-end-encrypted photos (the same
    zero-knowledge scheme as ``calendar``/``vault``: opaque ciphertext blobs +
    per-image keys wrapped under the master key). The shell component ships a
    topbar with two views — a default "Keep in touch" accordion of names and a
    full "All contacts" directory — reading ``GET /api/att/contacts/contacts`` and
    decrypting photos on view. One composite Tier-1 node, no shipped client code.
    """
    return _node("contacts", title=title)


def notes(*, title: str | None = None) -> UINode:
    """The notes UI — a list of markdown notes opening into a code-editor-style
    full editor.

    The backend stores each note's plaintext ``title`` and ``body`` (markdown) via
    ``GET/POST/PATCH/DELETE /api/att/notes/notes``. The shell component ships the
    whole experience: a card list, a "New note" button, an Edit button per note,
    and an editor view with a monospace text pane, a live markdown preview
    (pretext-laid-out), an editable editor font, line-wrap and line-number toggles,
    and a live word count. One composite Tier-1 node, no shipped client code.
    """
    return _node("notes", title=title)


def accounts(*, title: str | None = None) -> UINode:
    """The admin-only account management UI. The shell component lists child
    accounts, creates them (username + temp password/PIN + per-app checklist),
    edits each account's allowed apps, and deletes accounts — all via the
    ``/api/auth/admin/*`` endpoints (admin only). One composite Tier-1 node.
    """
    return _node("accounts", title=title)


def dropbox(*, title: str | None = None) -> UINode:
    """The dropbox UI — drop end-to-end-encrypted files onto another account.

    The cross-account sibling of the vault: the shell picks a recipient from the
    public-key directory (``GET /api/att/identity/keys``), encrypts each file with
    a fresh data key, seals the metadata header to the recipient's public key, and
    POSTs it to ``/api/att/dropbox/send``. Below, it lists *received* items
    (``/api/att/dropbox/items``), filterable by sending account, opening each
    sealed header with this account's secret key to decrypt + preview the blob.
    Received chat media (``source='chat'``) shows up here too. One composite Tier-1
    node; all crypto in the client.
    """
    return _node("dropbox", title=title)


def pomodoro(*, title: str | None = None) -> UINode:
    """The Pomodoro focus-timer UI — a server-authoritative session the shell
    drives and renders as a beautiful animated countdown.

    The backend owns the session (phase, end time, pause state, optional linked
    todo) via ``GET /state``, ``POST /start|pause|resume|reset`` and
    ``GET/PUT /settings``; it fires a notification when a running phase ends, even
    with no client open (durable scheduler). The shell component shows a circular
    countdown, lets you pick a todo to focus on (read from the todo attachment's
    ``items``), and on Start enters an immersive fullscreen view (real Fullscreen
    API where allowed, full-viewport overlay otherwise) with an Esc/exit control.
    One composite Tier-1 node, no shipped client code.
    """
    return _node("pomodoro", title=title)


def chat(*, title: str | None = None) -> UINode:
    """The chat UI — pick an account and exchange end-to-end-encrypted messages
    and media.

    Text is sealed to the recipient's public key (and to your own, so you can
    re-read your sent messages); media is encrypted and delivered through the
    dropbox (so it also appears in the recipient's dropbox, filterable by sender).
    The shell ships the whole experience: a thread list, a conversation view with
    chat bubbles and clustered media carousels, and a composer for text + multiple
    images at once. One composite Tier-1 node; all crypto in the client.
    """
    return _node("chat", title=title)


# --- action helpers ---------------------------------------------------------


def get(path: str) -> dict[str, Any]:
    return {"method": "GET", "path": path}


def post(path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"method": "POST", "path": path, "body": body or {}}


def delete(path: str) -> dict[str, Any]:
    return {"method": "DELETE", "path": path}


def patch(path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"method": "PATCH", "path": path, "body": body or {}}
