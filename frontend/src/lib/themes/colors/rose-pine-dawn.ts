import type { ColorTheme } from '../types';

// Rosé Pine Dawn — official light variant. https://rosepinetheme.com
export default {
	id: 'rose-pine-dawn',
	name: 'Rosé Pine Dawn',
	mode: 'light',
	tokens: {
		'--bg': '#faf4ed',
		'--surface': '#fffaf3',
		'--surface-2': '#f2e9e1',
		'--fg': '#575279',
		'--muted': '#9893a5',
		'--border-color': '#dfdad9',
		'--accent': '#907aa9',
		'--accent-fg': '#faf4ed',
		'--success': '#286983',
		'--success-fg': '#faf4ed',
		'--warn': '#ea9d34',
		'--warn-fg': '#575279',
		'--danger': '#b4637a',
		'--danger-fg': '#faf4ed',
		'--info': '#56949f',
		'--info-fg': '#faf4ed',
		'--overlay': 'rgba(87, 82, 121, 0.3)'
	}
} satisfies ColorTheme;
