import type { ColorTheme } from '../types';

// Palette: Catppuccin Latte (official spec) — light.
export default {
	id: 'catppuccin-latte',
	name: 'Catppuccin Latte',
	mode: 'light',
	tokens: {
		'--bg': '#eff1f5',
		'--surface': '#e6e9ef',
		'--surface-2': '#dce0e8',
		'--fg': '#4c4f69',
		'--muted': '#6c6f85',
		'--border-color': '#bcc0cc',
		'--accent': '#8839ef',
		'--accent-fg': '#eff1f5',
		'--success': '#40a02b',
		'--success-fg': '#eff1f5',
		'--warn': '#df8e1d',
		'--warn-fg': '#eff1f5',
		'--danger': '#d20f39',
		'--danger-fg': '#eff1f5',
		'--info': '#04a5e5',
		'--info-fg': '#eff1f5',
		'--overlay': 'rgba(76, 79, 105, 0.4)'
	}
} satisfies ColorTheme;
