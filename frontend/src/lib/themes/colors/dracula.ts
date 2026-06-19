import type { ColorTheme } from '../types';

// Palette: https://draculatheme.com/contribute (official spec)
export default {
	id: 'dracula',
	name: 'Dracula',
	mode: 'dark',
	tokens: {
		'--bg': '#282a36',
		'--surface': '#343746',
		'--surface-2': '#21222c',
		'--fg': '#f8f8f2',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#6272a4',
		'--border-color': '#44475a',
		'--accent': '#bd93f9',
		'--accent-fg': '#282a36',
		'--success': '#50fa7b',
		'--success-fg': '#282a36',
		'--warn': '#f1fa8c',
		'--warn-fg': '#282a36',
		'--danger': '#ff5555',
		'--danger-fg': '#282a36',
		'--info': '#8be9fd',
		'--info-fg': '#282a36',
		'--overlay': 'rgba(25, 26, 33, 0.8)'
	}
} satisfies ColorTheme;
