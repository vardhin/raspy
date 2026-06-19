import type { ColorTheme } from '../types';

// Catppuccin Macchiato. https://github.com/catppuccin/catppuccin
export default {
	id: 'catppuccin-macchiato',
	name: 'Catppuccin Macchiato',
	mode: 'dark',
	tokens: {
		'--bg': '#24273a',
		'--surface': '#363a4f',
		'--surface-2': '#1e2030',
		'--fg': '#cad3f5',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#8087a2',
		'--border-color': '#494d64',
		'--accent': '#c6a0f6',
		'--accent-fg': '#24273a',
		'--success': '#a6da95',
		'--success-fg': '#24273a',
		'--warn': '#eed49f',
		'--warn-fg': '#24273a',
		'--danger': '#ed8796',
		'--danger-fg': '#24273a',
		'--info': '#8aadf4',
		'--info-fg': '#24273a',
		'--overlay': 'rgba(30, 32, 48, 0.8)'
	}
} satisfies ColorTheme;
