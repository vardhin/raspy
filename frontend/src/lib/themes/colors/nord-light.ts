import type { ColorTheme } from '../types';

// Nord Light — built on the Nord "Snow Storm" palette. https://www.nordtheme.com
export default {
	id: 'nord-light',
	name: 'Nord (Light)',
	mode: 'light',
	tokens: {
		'--bg': '#eceff4',
		'--surface': '#ffffff',
		'--surface-2': '#e5e9f0',
		'--fg': '#2e3440',
		'--muted': '#4c566a',
		'--border-color': '#d8dee9',
		'--accent': '#5e81ac',
		'--accent-fg': '#eceff4',
		'--success': '#a3be8c',
		'--success-fg': '#2e3440',
		'--warn': '#ebcb8b',
		'--warn-fg': '#2e3440',
		'--danger': '#bf616a',
		'--danger-fg': '#eceff4',
		'--info': '#88c0d0',
		'--info-fg': '#2e3440',
		'--overlay': 'rgba(46, 52, 64, 0.3)'
	}
} satisfies ColorTheme;
