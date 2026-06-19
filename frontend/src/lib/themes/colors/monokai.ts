import type { ColorTheme } from '../types';

// Palette: Monokai (classic spec).
export default {
	id: 'monokai',
	name: 'Monokai',
	mode: 'dark',
	tokens: {
		'--bg': '#272822',
		'--surface': '#3e3d32',
		'--surface-2': '#1e1f1c',
		'--fg': '#f8f8f2',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#75715e',
		'--border-color': '#49483e',
		'--accent': '#a6e22e',
		'--accent-fg': '#272822',
		'--success': '#a6e22e',
		'--success-fg': '#272822',
		'--warn': '#e6db74',
		'--warn-fg': '#272822',
		'--danger': '#f92672',
		'--danger-fg': '#f8f8f2',
		'--info': '#66d9ef',
		'--info-fg': '#272822',
		'--overlay': 'rgba(30, 31, 28, 0.8)'
	}
} satisfies ColorTheme;
