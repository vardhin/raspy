import type { ColorTheme } from '../types';

// Ayu Light — warm off-white paper with a signature orange accent and teal/lime
// syntax hues. https://github.com/ayu-theme/ayu-colors (light)
export default {
	id: 'ayu-light',
	name: 'Ayu (Light)',
	mode: 'light',
	tokens: {
		'--bg': '#fcfcfc',
		'--surface': '#f3f4f5',
		'--surface-2': '#e7e8e9',
		'--fg': '#5c6166',
		'--muted': '#8a9199',
		'--border-color': '#d9dadb',
		'--accent': '#fa8d3e', // ayu orange
		'--accent-fg': '#ffffff',
		'--success': '#86b300', // lime
		'--success-fg': '#ffffff',
		'--warn': '#f2ae49', // amber
		'--warn-fg': '#5c6166',
		'--danger': '#f07171', // red
		'--danger-fg': '#ffffff',
		'--info': '#55b4d4', // cyan
		'--info-fg': '#ffffff',
		'--overlay': 'rgba(92, 97, 102, 0.28)'
	}
} satisfies ColorTheme;
