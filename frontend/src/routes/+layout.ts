// SPA mode: the spine serves the static bundle and lets the client router handle
// /a/[name] attachment routes via the index.html fallback. See plan/40-frontend.md.
export const ssr = false;
export const prerender = false;
export const trailingSlash = 'ignore';
