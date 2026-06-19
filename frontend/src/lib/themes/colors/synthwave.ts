import type { ColorTheme } from '../types';

// SynthWave '84 — neon-on-deep-purple retro aesthetic.
// https://github.com/robb0wen/synthwave-vscode
export default {
	id: 'synthwave',
	name: "SynthWave '84",
	mode: 'dark',
	tokens: {
		'--bg': '#262335',
		'--surface': '#2a2139',
		'--surface-2': '#1a1527',
		'--fg': '#f8f8f2',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#8b8499',
		'--border-color': '#463465',
		'--accent': '#ff7edb',
		'--accent-fg': '#262335',
		'--success': '#72f1b8',
		'--success-fg': '#262335',
		'--warn': '#fede5d',
		'--warn-fg': '#262335',
		'--danger': '#fe4450',
		'--danger-fg': '#262335',
		'--info': '#36f9f6',
		'--info-fg': '#262335',
		'--overlay': 'rgba(26, 21, 39, 0.82)'
	}
} satisfies ColorTheme;
