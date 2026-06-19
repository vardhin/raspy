import type { ColorTheme } from '../types';

// Palette: gruvbox by morhetz (official spec) — light, medium contrast.
export default {
	id: 'gruvbox-light',
	name: 'Gruvbox Light',
	mode: 'light',
	tokens: {
		'--bg': '#fbf1c7',
		'--surface': '#ebdbb2',
		'--surface-2': '#f9f5d7',
		'--fg': '#3c3836',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#7c6f64',
		'--border-color': '#d5c4a1',
		'--accent': '#af3a03',
		'--accent-fg': '#fbf1c7',
		'--success': '#79740e',
		'--success-fg': '#fbf1c7',
		'--warn': '#b57614',
		'--warn-fg': '#fbf1c7',
		'--danger': '#9d0006',
		'--danger-fg': '#fbf1c7',
		'--info': '#076678',
		'--info-fg': '#fbf1c7',
		'--overlay': 'rgba(60, 56, 54, 0.4)'
	}
} satisfies ColorTheme;
