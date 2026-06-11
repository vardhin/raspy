import type { ColorTheme } from '../types';

// Palette: Rosé Pine (official spec) — main (dark) variant.
export default {
	id: 'rose-pine',
	name: 'Rosé Pine',
	mode: 'dark',
	tokens: {
		'--bg': '#191724',
		'--surface': '#1f1d2e',
		'--surface-2': '#26233a',
		'--fg': '#e0def4',
		'--muted': '#908caa',
		'--border-color': '#403d52',
		'--accent': '#c4a7e7',
		'--accent-fg': '#191724',
		'--success': '#9ccfd8',
		'--success-fg': '#191724',
		'--warn': '#f6c177',
		'--warn-fg': '#191724',
		'--danger': '#eb6f92',
		'--danger-fg': '#191724',
		'--info': '#31748f',
		'--info-fg': '#e0def4',
		'--overlay': 'rgba(25, 23, 36, 0.8)'
	}
} satisfies ColorTheme;
