import type { ColorTheme } from '../types';

// Oxocarbon — based on IBM Carbon Design. https://github.com/nyoom-engineering/oxocarbon
export default {
	id: 'oxocarbon',
	name: 'Oxocarbon',
	mode: 'dark',
	tokens: {
		'--bg': '#161616',
		'--surface': '#262626',
		'--surface-2': '#0c0c0c',
		'--fg': '#f2f4f8',
		'--muted': '#8d8d8d',
		'--border-color': '#393939',
		'--accent': '#be95ff',
		'--accent-fg': '#161616',
		'--success': '#42be65',
		'--success-fg': '#161616',
		'--warn': '#ff832b',
		'--warn-fg': '#161616',
		'--danger': '#ff7eb6',
		'--danger-fg': '#161616',
		'--info': '#33b1ff',
		'--info-fg': '#161616',
		'--overlay': 'rgba(12, 12, 12, 0.8)'
	}
} satisfies ColorTheme;
