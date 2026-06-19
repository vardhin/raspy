import type { ColorTheme } from '../types';

// Cobalt2 — Wes Bos's deep-blue theme. https://github.com/wesbos/cobalt2-vscode
export default {
	id: 'cobalt2',
	name: 'Cobalt2',
	mode: 'dark',
	tokens: {
		'--bg': '#193549',
		'--surface': '#1f4662',
		'--surface-2': '#122738',
		'--fg': '#ffffff',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#7da7bc',
		'--border-color': '#2d5872',
		'--accent': '#ffc600',
		'--accent-fg': '#193549',
		'--success': '#3ad900',
		'--success-fg': '#193549',
		'--warn': '#ff9d00',
		'--warn-fg': '#193549',
		'--danger': '#ff628c',
		'--danger-fg': '#193549',
		'--info': '#9effff',
		'--info-fg': '#193549',
		'--overlay': 'rgba(18, 39, 56, 0.82)'
	}
} satisfies ColorTheme;
