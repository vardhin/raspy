# Raspy Frontend

This is the SvelteKit shell for Raspy. It is intentionally generic: the backend
serves `/api/manifest`, the shell renders the attachment UI descriptors in that
manifest, and each app talks to its own backend routes under `/api/att/<id>/`.

The production build is static and is served by the FastAPI spine from
`frontend/build/`. There is no Node server in production.

## Stack

- Svelte 5 runes mode
- SvelteKit with `@sveltejs/adapter-static`
- Vite
- Bun
- libsodium for the optional browser-to-spine channel and encrypted local data

## Development

Start the backend first:

```sh
cd ../backend
uv run raspy
```

Install frontend dependencies:

```sh
bun install
cp .env.example .env
```

If Vite is running on a different origin than the spine, set the backend base URL
in `.env`:

```sh
PUBLIC_API_BASE=http://127.0.0.1:49317
```

Then run:

```sh
bun run dev
```

Open the printed Vite URL, usually `http://localhost:5173`.

## Build and check

```sh
bun run check
bun run build
bun run preview
```

The build emits `frontend/build/` with an SPA fallback (`index.html`) so routes
like `/a/calendar` work when the FastAPI spine serves the bundle.

## Important pieces

- `src/routes/+layout.svelte` - auth gate, services, sidebar, mobile drawer.
- `src/routes/+page.svelte` - dashboard and connection summary.
- `src/routes/a/[id]/+page.svelte` - generic attachment app route.
- `src/lib/api.ts` - API base URL, CSRF, refresh retry, optional channel sealing.
- `src/lib/manifest/` - manifest fetch, ETag cache, per-user app visibility.
- `src/lib/renderer/` - declarative UI renderer for attachment descriptors.
- `src/lib/components/` - themed component primitives.
- `src/lib/themes/` - color palettes and concept themes.
- `src/lib/crypto/` - channel, vault, calendar media, and local key handling.

## Production

From the repo root:

```sh
scripts/build-frontend.sh
```

That forces `PUBLIC_API_BASE` empty by default so the shipped UI talks to its own
origin (`/api/...`). Restart the spine after building so it serves the updated
bundle.
