import type { ColorTheme } from '../types';

// Palette: Atom One Dark (official spec).
export default {
	id: 'one-dark',
	name: 'One Dark',
	mode: 'dark',
	tokens: {
		'--bg': '#282c34',
		'--surface': '#31363f',
		'--surface-2': '#21252b',
		'--fg': '#abb2bf',
		'--muted': '#5c6370',
		'--border-color': '#3e4451',
		'--accent': '#61afef',
		'--accent-fg': '#282c34',
		'--success': '#98c379',
		'--success-fg': '#282c34',
		'--warn': '#e5c07b',
		'--warn-fg': '#282c34',
		'--danger': '#e06c75',
		'--danger-fg': '#282c34',
		'--info': '#56b6c2',
		'--info-fg': '#282c34',
		'--overlay': 'rgba(33, 37, 43, 0.8)'
	}
} satisfies ColorTheme;
