import type { ColorTheme } from '../types';

// Atom One Light — cool grey paper with the signature One blue accent and
// muted syntax hues. https://github.com/atom/one-light-syntax
export default {
	id: 'one-light',
	name: 'One Light',
	mode: 'light',
	tokens: {
		'--bg': '#fafafa',
		'--surface': '#eaeaeb',
		'--surface-2': '#dbdbdc',
		'--fg': '#383a42',
		'--muted': '#a0a1a7',
		'--border-color': '#cfd0d2',
		'--accent': '#4078f2', // one blue
		'--accent-fg': '#ffffff',
		'--success': '#50a14f', // green
		'--success-fg': '#ffffff',
		'--warn': '#c18401', // yellow/amber
		'--warn-fg': '#ffffff',
		'--danger': '#e45649', // red
		'--danger-fg': '#ffffff',
		'--info': '#0184bc', // cyan
		'--info-fg': '#ffffff',
		'--overlay': 'rgba(56, 58, 66, 0.28)'
	}
} satisfies ColorTheme;
