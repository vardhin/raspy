import type { ColorTheme } from '../types';

// Tokyo Night Day — cool blue-tinted light variant; deep blue text on a soft
// slate-blue paper. https://github.com/folke/tokyonight.nvim (day)
export default {
	id: 'tokyo-night-light',
	name: 'Tokyo Night Day',
	mode: 'light',
	tokens: {
		'--bg': '#e1e2e7', // day bg
		'--surface': '#d0d5e3', // bg_dark / float
		'--surface-2': '#c4c8da', // bg_highlight
		'--fg': '#3760bf', // day fg (blue-leaning)
		'--muted': '#7782ac', // comment
		'--border-color': '#b6bcd1',
		'--accent': '#2e7de9', // blue
		'--accent-fg': '#e1e2e7',
		'--success': '#587539', // green
		'--success-fg': '#e1e2e7',
		'--warn': '#8c6c3e', // yellow/brown
		'--warn-fg': '#e1e2e7',
		'--danger': '#f52a65', // red/magenta
		'--danger-fg': '#e1e2e7',
		'--info': '#007197', // cyan
		'--info-fg': '#e1e2e7',
		'--overlay': 'rgba(55, 96, 191, 0.26)'
	}
} satisfies ColorTheme;
