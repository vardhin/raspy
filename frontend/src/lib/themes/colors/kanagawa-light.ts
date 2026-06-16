import type { ColorTheme } from '../types';

// Kanagawa Lotus — official light variant. https://github.com/rebelot/kanagawa.nvim
export default {
	id: 'kanagawa-light',
	name: 'Kanagawa (Lotus)',
	mode: 'light',
	tokens: {
		'--bg': '#f2ecbc',
		'--surface': '#e7dba0',
		'--surface-2': '#e4d794',
		'--fg': '#545464',
		'--muted': '#8a8980',
		'--border-color': '#cabd80',
		'--accent': '#4d699b',
		'--accent-fg': '#f2ecbc',
		'--success': '#6f894e',
		'--success-fg': '#f2ecbc',
		'--warn': '#cc6d00',
		'--warn-fg': '#f2ecbc',
		'--danger': '#c84053',
		'--danger-fg': '#f2ecbc',
		'--info': '#597b75',
		'--info-fg': '#f2ecbc',
		'--overlay': 'rgba(84, 84, 100, 0.32)'
	}
} satisfies ColorTheme;
