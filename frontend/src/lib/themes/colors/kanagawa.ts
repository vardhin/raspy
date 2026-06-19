import type { ColorTheme } from '../types';

// Palette: Kanagawa by rebelot (official spec) — wave (dark).
export default {
	id: 'kanagawa',
	name: 'Kanagawa',
	mode: 'dark',
	tokens: {
		'--bg': '#1f1f28',
		'--surface': '#2a2a37',
		'--surface-2': '#16161d',
		'--fg': '#dcd7ba',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#727169',
		'--border-color': '#363646',
		'--accent': '#7e9cd8',
		'--accent-fg': '#1f1f28',
		'--success': '#98bb6c',
		'--success-fg': '#1f1f28',
		'--warn': '#e6c384',
		'--warn-fg': '#1f1f28',
		'--danger': '#e82424',
		'--danger-fg': '#dcd7ba',
		'--info': '#7fb4ca',
		'--info-fg': '#1f1f28',
		'--overlay': 'rgba(22, 22, 29, 0.8)'
	}
} satisfies ColorTheme;
