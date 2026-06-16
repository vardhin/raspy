import type { ColorTheme } from '../types';

// GitHub Dark (default). https://github.com/primer/github-vscode-theme
export default {
	id: 'github-dark',
	name: 'GitHub Dark',
	mode: 'dark',
	tokens: {
		'--bg': '#0d1117',
		'--surface': '#161b22',
		'--surface-2': '#010409',
		'--fg': '#e6edf3',
		'--muted': '#8b949e',
		'--border-color': '#30363d',
		'--accent': '#58a6ff',
		'--accent-fg': '#0d1117',
		'--success': '#3fb950',
		'--success-fg': '#0d1117',
		'--warn': '#d29922',
		'--warn-fg': '#0d1117',
		'--danger': '#f85149',
		'--danger-fg': '#0d1117',
		'--info': '#79c0ff',
		'--info-fg': '#0d1117',
		'--overlay': 'rgba(1, 4, 9, 0.8)'
	}
} satisfies ColorTheme;
