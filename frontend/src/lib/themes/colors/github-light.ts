import type { ColorTheme } from '../types';

// GitHub Light (default). Crisp neutral grey UI with GitHub's blue accent.
// https://github.com/primer/github-vscode-theme
export default {
	id: 'github-light',
	name: 'GitHub Light',
	mode: 'light',
	tokens: {
		'--bg': '#ffffff',
		'--surface': '#f6f8fa',
		'--surface-2': '#eaeef2',
		'--fg': '#1f2328',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#656d76',
		'--border-color': '#d0d7de',
		'--accent': '#0969da',
		'--accent-fg': '#ffffff',
		'--success': '#1a7f37',
		'--success-fg': '#ffffff',
		'--warn': '#9a6700',
		'--warn-fg': '#ffffff',
		'--danger': '#cf222e',
		'--danger-fg': '#ffffff',
		'--info': '#0550ae',
		'--info-fg': '#ffffff',
		'--overlay': 'rgba(31, 35, 40, 0.28)'
	}
} satisfies ColorTheme;
