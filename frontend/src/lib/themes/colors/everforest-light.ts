import type { ColorTheme } from '../types';

// Everforest Light (medium). https://github.com/sainnhe/everforest
export default {
	id: 'everforest-light',
	name: 'Everforest (Light)',
	mode: 'light',
	tokens: {
		'--bg': '#fdf6e3',
		'--surface': '#f4f0d9',
		'--surface-2': '#efebd4',
		'--fg': '#5c6a72',
		'--muted': '#939f91',
		'--border-color': '#e0dcc7',
		'--accent': '#8da101',
		'--accent-fg': '#fdf6e3',
		'--success': '#35a77c',
		'--success-fg': '#fdf6e3',
		'--warn': '#dfa000',
		'--warn-fg': '#fdf6e3',
		'--danger': '#f85552',
		'--danger-fg': '#fdf6e3',
		'--info': '#3a94c5',
		'--info-fg': '#fdf6e3',
		'--overlay': 'rgba(92, 106, 114, 0.3)'
	}
} satisfies ColorTheme;
