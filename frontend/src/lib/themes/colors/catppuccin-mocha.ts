import type { ColorTheme } from '../types';

// Palette: Catppuccin Mocha (official spec).
export default {
	id: 'catppuccin-mocha',
	name: 'Catppuccin Mocha',
	mode: 'dark',
	tokens: {
		'--bg': '#1e1e2e',
		'--surface': '#313244',
		'--surface-2': '#181825',
		'--fg': '#cdd6f4',
		'--muted': '#a6adc8',
		'--border-color': '#45475a',
		'--accent': '#cba6f7',
		'--accent-fg': '#1e1e2e',
		'--success': '#a6e3a1',
		'--success-fg': '#1e1e2e',
		'--warn': '#f9e2af',
		'--warn-fg': '#1e1e2e',
		'--danger': '#f38ba8',
		'--danger-fg': '#1e1e2e',
		'--info': '#89dceb',
		'--info-fg': '#1e1e2e',
		'--overlay': 'rgba(24, 24, 37, 0.8)'
	}
} satisfies ColorTheme;
