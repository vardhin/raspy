import type { ColorTheme } from '../types';

// Nord Light — the cool blue-grey "Snow Storm" base with Frost/Aurora accents.
// Surfaces stay in the snow-storm range so it reads distinctly cool, not white.
// https://www.nordtheme.com
export default {
	id: 'nord-light',
	name: 'Nord (Light)',
	mode: 'light',
	tokens: {
		'--bg': '#eceff4', // nord6
		'--surface': '#e5e9f0', // nord5
		'--surface-2': '#d8dee9', // nord4
		'--fg': '#2e3440', // nord0
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#4c566a', // nord3
		'--border-color': '#c2cad6',
		'--accent': '#5e81ac', // nord10 (frost blue)
		'--accent-fg': '#eceff4',
		'--success': '#a3be8c', // nord14
		'--success-fg': '#2e3440',
		'--warn': '#d08770', // nord12 (orange) — more distinct than yellow
		'--warn-fg': '#2e3440',
		'--danger': '#bf616a', // nord11
		'--danger-fg': '#eceff4',
		'--info': '#88c0d0', // nord8
		'--info-fg': '#2e3440',
		'--overlay': 'rgba(46, 52, 64, 0.28)'
	}
} satisfies ColorTheme;
