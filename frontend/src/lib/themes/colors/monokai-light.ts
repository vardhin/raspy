import type { ColorTheme } from '../types';

// Monokai Light — a light reinterpretation of the classic Monokai palette.
export default {
	id: 'monokai-light',
	name: 'Monokai (Light)',
	mode: 'light',
	tokens: {
		'--bg': '#fafafa',
		'--surface': '#ffffff',
		'--surface-2': '#f0f0f0',
		'--fg': '#2c292d',
		'--muted': '#74705d',
		'--border-color': '#e0e0e0',
		'--accent': '#e14775',
		'--accent-fg': '#ffffff',
		'--success': '#67961a',
		'--success-fg': '#ffffff',
		'--warn': '#cc8b00',
		'--warn-fg': '#2c292d',
		'--danger': '#e0382e',
		'--danger-fg': '#ffffff',
		'--info': '#1f9ec4',
		'--info-fg': '#ffffff',
		'--overlay': 'rgba(44, 41, 45, 0.32)'
	}
} satisfies ColorTheme;
