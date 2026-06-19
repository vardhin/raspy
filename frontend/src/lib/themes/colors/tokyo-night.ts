import type { ColorTheme } from '../types';

// Palette: Tokyo Night by enkia (official spec).
export default {
	id: 'tokyo-night',
	name: 'Tokyo Night',
	mode: 'dark',
	tokens: {
		'--bg': '#1a1b26',
		'--surface': '#24283b',
		'--surface-2': '#16161e',
		'--fg': '#c0caf5',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#565f89',
		'--border-color': '#3b4261',
		'--accent': '#7aa2f7',
		'--accent-fg': '#1a1b26',
		'--success': '#9ece6a',
		'--success-fg': '#1a1b26',
		'--warn': '#e0af68',
		'--warn-fg': '#1a1b26',
		'--danger': '#f7768e',
		'--danger-fg': '#1a1b26',
		'--info': '#7dcfff',
		'--info-fg': '#1a1b26',
		'--overlay': 'rgba(22, 22, 30, 0.8)'
	}
} satisfies ColorTheme;
