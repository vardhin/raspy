# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — bundle the Raspy spine + built frontend into ONE binary.

Run from backend/ AFTER the frontend has been built into frontend/build/:

    cd frontend && bun install && bun run build      # produces ../frontend/build
    cd ../backend && uv run pyinstaller raspy.spec   # produces dist/raspy[.exe]

Why a spec (not a one-line `pyinstaller raspy/__main__.py`):

  * Uvicorn is launched with the IMPORT STRING "raspy.app:app" (see
    raspy/__main__.py), so PyInstaller's static import follower never sees
    raspy.app / raspy.core.* / the attachments. We pull them in explicitly with
    collect_submodules so every attachment is present in the frozen binary.
  * uvicorn[standard] loads uvloop / httptools / websockets lazily by name; those
    are added as hidden imports.
  * The frontend build is shipped as a datadir at `frontend/` inside the bundle;
    config._default_static_dir() resolves it from sys._MEIPASS when frozen.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# backend/ is the spec's directory; the frontend build sits at ../frontend/build.
HERE = Path(SPECPATH)            # noqa: F821 (SPECPATH injected by PyInstaller)
FRONTEND_BUILD = HERE.parent / "frontend" / "build"

if not (FRONTEND_BUILD / "index.html").is_file():
    raise SystemExit(
        f"frontend build not found at {FRONTEND_BUILD}. Build it first:\n"
        "  cd frontend && bun install && bun run build"
    )

# Pull in everything discovered/imported by string so nothing is missing at runtime.
hidden = []
hidden += collect_submodules("raspy")            # app, core.*, all attachments
hidden += collect_submodules("uvicorn")          # protocol/loop impls loaded by name
hidden += [
    "uvloop",
    "httptools",
    "websockets",
    "websockets.legacy",
    "py_vapid",
    "pywebpush",
]

# Ship the built SPA as datadir `frontend/` (matches config._default_static_dir()).
datas = [(str(FRONTEND_BUILD), "frontend")]
# argon2 / cryptography ship compiled bits + cffi modules; let hooks collect them.
datas += collect_data_files("argon2")

block_cipher = None

a = Analysis(
    ["raspy/__main__.py"],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "httpx"],   # not needed at runtime
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="raspy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,                  # it's a server; keep stdout/stderr for logs
    disable_windowed_traceback=False,
    target_arch=None,              # CI sets arch via the runner; PyInstaller is native
    codesign_identity=None,
    entitlements_file=None,
)
