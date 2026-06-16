import type { ColorTheme } from '../types';

// Atom One Light — the official light counterpart of One Dark.
export default {
	id: 'one-light',
	name: 'One Light',
	mode: 'light',
	tokens: {
		'--bg': '#fafafa',
		'--surface': '#ffffff',
		'--surface-2': '#f0f0f1',
		'--fg': '#383a42',
		'--muted': '#a0a1a7',
		'--border-color': '#e5e5e6',
		'--accent': '#4078f2',
		'--accent-fg': '#ffffff',
		'--success': '#50a14f',
		'--success-fg': '#ffffff',
		'--warn': '#c18401',
		'--warn-fg': '#ffffff',
		'--danger': '#e45649',
		'--danger-fg': '#ffffff',
		'--info': '#0184bc',
		'--info-fg': '#ffffff',
		'--overlay': 'rgba(56, 58, 66, 0.3)'
	}
} satisfies ColorTheme;
