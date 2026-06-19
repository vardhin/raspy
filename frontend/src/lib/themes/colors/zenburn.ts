import type { ColorTheme } from '../types';

// Zenburn — the classic low-contrast warm earth-tone theme.
// https://github.com/jnurmine/Zenburn
export default {
	id: 'zenburn',
	name: 'Zenburn',
	mode: 'dark',
	tokens: {
		'--bg': '#3f3f3f',
		'--surface': '#4f4f4f',
		'--surface-2': '#353535',
		'--fg': '#dcdccc',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#9f9f8f',
		'--border-color': '#5f5f5f',
		'--accent': '#f0dfaf',
		'--accent-fg': '#3f3f3f',
		'--success': '#7f9f7f',
		'--success-fg': '#3f3f3f',
		'--warn': '#e3ceab',
		'--warn-fg': '#3f3f3f',
		'--danger': '#cc9393',
		'--danger-fg': '#3f3f3f',
		'--info': '#8cd0d3',
		'--info-fg': '#3f3f3f',
		'--overlay': 'rgba(53, 53, 53, 0.8)'
	}
} satisfies ColorTheme;
