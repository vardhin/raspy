import type { ColorTheme } from '../types';

// Gruvbox Material (dark, medium) — softer contrast take on Gruvbox.
// https://github.com/sainnhe/gruvbox-material
export default {
	id: 'gruvbox-material',
	name: 'Gruvbox Material',
	mode: 'dark',
	tokens: {
		'--bg': '#282828',
		'--surface': '#32302f',
		'--surface-2': '#1d2021',
		'--fg': '#d4be98',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#928374',
		'--border-color': '#45403d',
		'--accent': '#a9b665',
		'--accent-fg': '#282828',
		'--success': '#89b482',
		'--success-fg': '#282828',
		'--warn': '#d8a657',
		'--warn-fg': '#282828',
		'--danger': '#ea6962',
		'--danger-fg': '#282828',
		'--info': '#7daea3',
		'--info-fg': '#282828',
		'--overlay': 'rgba(29, 32, 33, 0.8)'
	}
} satisfies ColorTheme;
