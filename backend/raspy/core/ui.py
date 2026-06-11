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


def badge(value: str, *, variant: str = "neutral", bind: str | None = None) -> UINode:
    return _node("badge", text=value, variant=variant, bind=bind)


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
) -> UINode:
    return _node("button", text=label, action=action, variant=variant)


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


# --- action helpers ---------------------------------------------------------


def get(path: str) -> dict[str, Any]:
    return {"method": "GET", "path": path}


def post(path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"method": "POST", "path": path, "body": body or {}}


def delete(path: str) -> dict[str, Any]:
    return {"method": "DELETE", "path": path}


def patch(path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"method": "PATCH", "path": path, "body": body or {}}
