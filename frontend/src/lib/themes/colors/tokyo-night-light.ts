import type { ColorTheme } from '../types';

// Tokyo Night Day — official light variant. https://github.com/enkia/tokyo-night-vscode-theme
export default {
	id: 'tokyo-night-light',
	name: 'Tokyo Night Day',
	mode: 'light',
	tokens: {
		'--bg': '#e1e2e7',
		'--surface': '#e9e9ed',
		'--surface-2': '#d5d6db',
		'--fg': '#3760bf',
		'--muted': '#848cb5',
		'--border-color': '#c4c8da',
		'--accent': '#2e7de9',
		'--accent-fg': '#e1e2e7',
		'--success': '#587539',
		'--success-fg': '#e1e2e7',
		'--warn': '#8c6c3e',
		'--warn-fg': '#e1e2e7',
		'--danger': '#f52a65',
		'--danger-fg': '#e1e2e7',
		'--info': '#007197',
		'--info-fg': '#e1e2e7',
		'--overlay': 'rgba(55, 96, 191, 0.28)'
	}
} satisfies ColorTheme;
