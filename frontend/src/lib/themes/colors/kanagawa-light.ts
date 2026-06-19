import type { ColorTheme } from '../types';

// Kanagawa Lotus — the official light variant: a warm sand/parchment base
// (lotusInk on lotusWhite) with muted indigo and earthy accents.
// https://github.com/rebelot/kanagawa.nvim
export default {
	id: 'kanagawa-light',
	name: 'Kanagawa (Lotus)',
	mode: 'light',
	tokens: {
		'--bg': '#f2ecbc', // lotusWhite3
		'--surface': '#e7dba0', // lotusWhite4
		'--surface-2': '#e4d794', // lotusWhite5
		'--fg': '#545464', // lotusInk1
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#766b90', // lotusViolet3 / gray ink
		'--border-color': '#d5cea3', // lotusWhite2
		'--accent': '#4d699b', // lotusBlue4 (indigo)
		'--accent-fg': '#f2ecbc',
		'--success': '#6f894e', // lotusGreen
		'--success-fg': '#f2ecbc',
		'--warn': '#cc6d00', // lotusOrange
		'--warn-fg': '#f2ecbc',
		'--danger': '#c84053', // lotusRed
		'--danger-fg': '#f2ecbc',
		'--info': '#597b75', // lotusAqua
		'--info-fg': '#f2ecbc',
		'--overlay': 'rgba(84, 84, 100, 0.3)'
	}
} satisfies ColorTheme;
