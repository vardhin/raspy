import type { ColorTheme } from '../types';

// Material Theme — Ocean. https://github.com/material-theme/vsc-material-theme
export default {
	id: 'material-ocean',
	name: 'Material Ocean',
	mode: 'dark',
	tokens: {
		'--bg': '#0f111a',
		'--surface': '#1a1c25',
		'--surface-2': '#090b10',
		'--fg': '#a6accd',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#717cb4',
		'--border-color': '#2a2e3e',
		'--accent': '#82aaff',
		'--accent-fg': '#0f111a',
		'--success': '#c3e88d',
		'--success-fg': '#0f111a',
		'--warn': '#ffcb6b',
		'--warn-fg': '#0f111a',
		'--danger': '#f07178',
		'--danger-fg': '#0f111a',
		'--info': '#89ddff',
		'--info-fg': '#0f111a',
		'--overlay': 'rgba(9, 11, 16, 0.8)'
	}
} satisfies ColorTheme;
