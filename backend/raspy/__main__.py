"""CLI entry: ``raspy`` / ``python -m raspy``.

In a source checkout there are three console scripts (``raspy``, ``raspy-auth``,
``raspy-vapid`` — see pyproject). The frozen single-file binary only has ONE
entry point, so this dispatches the same tools as subcommands:

    raspy                 run the spine (default, no args)
    raspy serve           run the spine (explicit)
    raspy auth <args...>  the raspy-auth admin CLI (create-account, set-pin, …)
    raspy vapid           generate a VAPID keypair
    raspy version         print the version and exit

The installer (scripts/install.*) relies on `raspy auth create-account` and
`raspy vapid` so a single downloaded binary can do first-run setup with no
separate scripts.

NOTE: PyInstaller runs this file as a top-level script (module name "__main__"),
so it has no parent package — relative imports would fail in the frozen binary.
Use absolute ``raspy.*`` imports here only.
"""

from __future__ import annotations

import sys

from raspy import __version__


def _serve() -> None:
    import uvicorn

    from raspy.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "raspy.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] == "serve":
        _serve()
        return

    cmd = argv[0]
    # Re-slice argv so the delegated CLIs see only their own args.
    rest = argv[1:]

    if cmd == "auth":
        from raspy.core.auth.cli import main as auth_main

        sys.argv = ["raspy-auth", *rest]
        auth_main()
    elif cmd == "vapid":
        from raspy.vapid import main as vapid_main

        sys.argv = ["raspy-vapid", *rest]
        vapid_main()
    elif cmd in ("version", "--version", "-V"):
        print(__version__)
    else:
        # Unknown first arg → treat as serving (back-compat) but warn to stderr.
        print(
            f"unknown command {cmd!r}; running the spine. "
            "Valid: serve | auth | vapid | version",
            file=sys.stderr,
        )
        _serve()


if __name__ == "__main__":
    main()
