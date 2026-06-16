import type { ColorTheme } from '../types';

// Carbonfox — the dark Nightfox variant inspired by IBM Carbon.
// https://github.com/EdenEast/nightfox.nvim
export default {
	id: 'carbonfox',
	name: 'Carbonfox',
	mode: 'dark',
	tokens: {
		'--bg': '#161616',
		'--surface': '#252525',
		'--surface-2': '#0c0c0c',
		'--fg': '#f2f4f8',
		'--muted': '#7b7c7e',
		'--border-color': '#353535',
		'--accent': '#78a9ff',
		'--accent-fg': '#161616',
		'--success': '#25be6a',
		'--success-fg': '#161616',
		'--warn': '#08bdba',
		'--warn-fg': '#161616',
		'--danger': '#ee5396',
		'--danger-fg': '#161616',
		'--info': '#33b1ff',
		'--info-fg': '#161616',
		'--overlay': 'rgba(12, 12, 12, 0.8)'
	}
} satisfies ColorTheme;
