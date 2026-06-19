// One-time (re-runnable) fetcher for the bundled font set.
//
// Downloads each family's woff2 (weights 400 & 700) from Google's keyless CSS API
// into static/fonts/<id>/, so the app ships the fonts and never reaches out to
// Google at runtime (cf. backend/raspy/attachments/_dailyvibe/fonts.py, which does
// the same trick server-side for the Vibe app). The committed .woff2 files are the
// source of truth; this script just regenerates them.
//
//   node scripts/fetch-fonts.mjs
//
// The font *registry* (id, display name, css stack, category) lives in
// src/lib/themes/fonts/*.ts and is the single source the app reads — keep the ids
// here in sync with the FONTS list below (same ids → same folder names).

import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, '..', 'static', 'fonts');

const CSS_API = 'https://fonts.googleapis.com/css2';
// Modern UA so Google serves woff2.
const UA =
	'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36';

// id → Google family name. id is the folder + the registry id.
const FONTS = [
	// sans
	['inter', 'Inter'],
	['manrope', 'Manrope'],
	['work-sans', 'Work Sans'],
	['dm-sans', 'DM Sans'],
	['nunito', 'Nunito'],
	['poppins', 'Poppins'],
	['rubik', 'Rubik'],
	['outfit', 'Outfit'],
	['plus-jakarta-sans', 'Plus Jakarta Sans'],
	['space-grotesk', 'Space Grotesk'],
	// serif
	['merriweather', 'Merriweather'],
	['lora', 'Lora'],
	['source-serif-4', 'Source Serif 4'],
	['playfair-display', 'Playfair Display'],
	['fraunces', 'Fraunces'],
	['libre-baskerville', 'Libre Baskerville'],
	// mono
	['jetbrains-mono', 'JetBrains Mono'],
	['fira-code', 'Fira Code'],
	['ibm-plex-mono', 'IBM Plex Mono'],
	['space-mono', 'Space Mono'],
	// display
	['righteous', 'Righteous'],
	['orbitron', 'Orbitron'],
	['bebas-neue', 'Bebas Neue'],
	// handwriting
	['caveat', 'Caveat'],
	['pacifico', 'Pacifico']
];

const FONT_URL_RE = /url\((https:\/\/fonts\.gstatic\.com\/[^)]+\.woff2)\)/g;

async function fetchText(url) {
	const res = await fetch(url, { headers: { 'User-Agent': UA } });
	if (!res.ok) throw new Error(`${res.status} ${url}`);
	return res.text();
}

async function fetchBytes(url) {
	const res = await fetch(url, { headers: { 'User-Agent': UA } });
	if (!res.ok) throw new Error(`${res.status} ${url}`);
	return Buffer.from(await res.arrayBuffer());
}

async function one(id, family) {
	const dir = join(OUT, id);
	await mkdir(dir, { recursive: true });
	const qs = new URLSearchParams({ family: `${family}:wght@400;700`, display: 'swap' });
	const css = await fetchText(`${CSS_API}?${qs}`);

	// Grab the distinct woff2 urls (Google emits several per-subset; we just take
	// the first 400 and first 700 we can attribute, which the latin subset covers).
	const urls = [...css.matchAll(FONT_URL_RE)].map((m) => m[1]);
	// Heuristic: split the CSS into @font-face blocks and pull weight + url per block,
	// keeping the first url seen for each of 400/700 (latin subset comes first).
	const blocks = css.split('@font-face');
	const picked = {};
	for (const b of blocks) {
		const w = b.match(/font-weight:\s*(\d+)/)?.[1];
		const u = b.match(/url\((https:\/\/fonts\.gstatic\.com\/[^)]+\.woff2)\)/)?.[1];
		if (w && u && !picked[w]) picked[w] = u;
	}
	if (!picked['400'] && urls[0]) picked['400'] = urls[0];

	const written = [];
	for (const [weight, url] of Object.entries(picked)) {
		const bytes = await fetchBytes(url);
		const file = `${weight}.woff2`;
		await writeFile(join(dir, file), bytes);
		written.push(file);
	}
	console.log(`✓ ${id} (${family}): ${written.join(', ')}`);
}

async function main() {
	await mkdir(OUT, { recursive: true });
	for (const [id, family] of FONTS) {
		try {
			await one(id, family);
		} catch (e) {
			console.error(`✗ ${id} (${family}):`, e.message);
		}
	}
	console.log(`\nDone → ${OUT}`);
}

main();
