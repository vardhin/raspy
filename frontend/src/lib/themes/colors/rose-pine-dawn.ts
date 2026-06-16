import type { ColorTheme } from '../types';

// Rosé Pine Dawn — warm rose-cream base with mauve/iris/pine accents. The whole
// palette leans pink-violet, so surfaces carry that rose tint rather than going
// flat white. https://rosepinetheme.com (Dawn variant)
export default {
	id: 'rose-pine-dawn',
	name: 'Rosé Pine Dawn',
	mode: 'light',
	tokens: {
		'--bg': '#faf4ed', // base
		'--surface': '#fffaf3', // surface
		'--surface-2': '#f2e9e1', // overlay
		'--fg': '#575279', // text (muted plum)
		'--muted': '#797593', // subtle
		'--border-color': '#dfdad9', // highlight med
		'--accent': '#907aa9', // iris
		'--accent-fg': '#fffaf3',
		'--success': '#56949f', // foam
		'--success-fg': '#fffaf3',
		'--warn': '#ea9d34', // gold
		'--warn-fg': '#575279',
		'--danger': '#b4637a', // love (rose)
		'--danger-fg': '#fffaf3',
		'--info': '#286983', // pine
		'--info-fg': '#fffaf3',
		'--overlay': 'rgba(87, 82, 121, 0.28)'
	}
} satisfies ColorTheme;
