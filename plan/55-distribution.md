# Distribution & self-update

Goal: make Raspy installable and updatable by a non-technical user — no Python,
no Node, no `uv`, no SSH. The spine is already one local server (API + static
frontend on one origin); this packages that into a single binary and wraps it in
a frictionless install + update story.

## 1. One self-contained binary

`backend/raspy.spec` bundles the FastAPI spine **and** the built SvelteKit frontend
into a single PyInstaller executable per platform.

- The frontend build is shipped as a datadir inside the bundle; at runtime
  `config._default_static_dir()` resolves it from `sys._MEIPASS` when frozen
  (falling back to `frontend/build/` for a source checkout).
- The frozen binary's default data dir is a per-user OS location (so a binary in
  a read-only prefix still works): `~/.local/share/raspy` (Linux),
  `~/Library/Application Support/raspy` (macOS), `%APPDATA%\raspy` (Windows).
  Override with `RASPY_DATA_DIR`.
- One entry point dispatches subcommands (`raspy serve|auth|vapid|version`) since
  a single binary can't expose three console scripts.

## 2. Releases via GitHub Actions

`.github/workflows/release.yml`, triggered by a `v*` tag (or manual dispatch):

- Matrix over linux x64/arm64, macOS x64/arm64, windows x64. The `arm64` Linux
  runner is the Raspberry Pi target.
- Builds the frontend, then the binary, smoke-tests `raspy version`, and uploads
  each `raspy-<os>-<arch>` artifact.
- A publish job collects them, writes `SHA256SUMS` (the installer + updater
  verify against this) and `latest.json` (`{version, assets}`, read by the
  in-app updater), and attaches all three to the GitHub Release.

`scripts/release.sh` bumps `__version__` (the single source of truth — pyproject
reads it dynamically), tags, and pushes to fire the workflow.

## 3. The installer

`scripts/install.sh` (Linux/macOS) and `scripts/install.ps1` (Windows), both
curl/irm-pipeable, depend on nothing but the OS shell + curl/wget. They:

1. detect os/arch and download the matching release asset,
2. verify it against `SHA256SUMS`,
3. install it to a sane prefix,
4. generate VAPID keys into `config.toml` (push works out of the box),
5. create the first admin account interactively (`auth create-account --stdin`),
6. optionally register a boot service (systemd / launchd / Windows service),
7. start it and print the local URL.

They are **idempotent**: on a machine that already has Raspy they show a menu —
update / uninstall / cancel. Uninstall stops + removes the service and binary and
asks before deleting the data dir.

## 4. Self-update (notify + one-click)

`core/updater.py` + `core/update_routes.py`:

- A background task periodically reads `latest.json` and compares it to
  `__version__`. When newer, it raises an `update.available` event + a
  notification — the UI shows an admin-only banner (`UpdateBanner.svelte`).
- **Nothing downloads automatically.** On the user clicking *Update now*, the
  spine downloads the platform asset, verifies it against `SHA256SUMS`, swaps it
  atomically (rename-aside on Windows where the live exe is locked), and asks the
  service manager to restart — then the new version comes up. The server never
  restarts silently.
- A source checkout reports `updatable: false`; there's no single artifact to
  swap.
