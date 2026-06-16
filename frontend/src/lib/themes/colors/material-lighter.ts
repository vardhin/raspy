import type { ColorTheme } from '../types';

// Material Theme — Lighter. The official light counterpart to Material Ocean:
// a clean blue-grey paper with Material accents.
// https://github.com/material-theme/vsc-material-theme
export default {
	id: 'material-lighter',
	name: 'Material Lighter',
	mode: 'light',
	tokens: {
		'--bg': '#fafafa',
		'--surface': '#eeeeee',
		'--surface-2': '#e7eaec',
		'--fg': '#546e7a',
		'--muted': '#90a4ae',
		'--border-color': '#d3dade',
		'--accent': '#6182b8', // blue
		'--accent-fg': '#ffffff',
		'--success': '#91b859', // green
		'--success-fg': '#ffffff',
		'--warn': '#f6a434', // orange
		'--warn-fg': '#ffffff',
		'--danger': '#e53935', // red
		'--danger-fg': '#ffffff',
		'--info': '#39adb5', // cyan
		'--info-fg': '#ffffff',
		'--overlay': 'rgba(84, 110, 122, 0.28)'
	}
} satisfies ColorTheme;
