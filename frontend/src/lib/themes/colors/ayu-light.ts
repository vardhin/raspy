import type { ColorTheme } from '../types';

// Ayu Light — official light variant. https://github.com/ayu-theme/ayu-colors
export default {
	id: 'ayu-light',
	name: 'Ayu (Light)',
	mode: 'light',
	tokens: {
		'--bg': '#fcfcfc',
		'--surface': '#ffffff',
		'--surface-2': '#f3f4f5',
		'--fg': '#5c6166',
		'--muted': '#8a9199',
		'--border-color': '#e7e8e9',
		'--accent': '#ff9940',
		'--accent-fg': '#ffffff',
		'--success': '#86b300',
		'--success-fg': '#ffffff',
		'--warn': '#f2ae49',
		'--warn-fg': '#5c6166',
		'--danger': '#f07171',
		'--danger-fg': '#ffffff',
		'--info': '#55b4d4',
		'--info-fg': '#ffffff',
		'--overlay': 'rgba(92, 97, 102, 0.3)'
	}
} satisfies ColorTheme;
