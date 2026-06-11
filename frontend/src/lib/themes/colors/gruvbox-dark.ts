import type { ColorTheme } from '../types';

// Palette: gruvbox by morhetz (official spec) — dark, medium contrast.
export default {
	id: 'gruvbox-dark',
	name: 'Gruvbox Dark',
	mode: 'dark',
	tokens: {
		'--bg': '#282828',
		'--surface': '#3c3836',
		'--surface-2': '#1d2021',
		'--fg': '#ebdbb2',
		'--muted': '#a89984',
		'--border-color': '#504945',
		'--accent': '#fe8019',
		'--accent-fg': '#282828',
		'--success': '#b8bb26',
		'--success-fg': '#282828',
		'--warn': '#fabd2f',
		'--warn-fg': '#282828',
		'--danger': '#fb4934',
		'--danger-fg': '#282828',
		'--info': '#83a598',
		'--info-fg': '#282828',
		'--overlay': 'rgba(29, 32, 33, 0.8)'
	}
} satisfies ColorTheme;
