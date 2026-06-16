import type { ColorTheme } from '../types';

// Alucard — Dracula's official light theme. Warm cream paper with the Dracula
// purple/pink/green accents darkened for contrast on light.
// https://draculatheme.com/alucard
export default {
	id: 'dracula-light',
	name: 'Alucard (Dracula Light)',
	mode: 'light',
	tokens: {
		'--bg': '#fffbeb', // alucard background
		'--surface': '#f5f1e0', // current line
		'--surface-2': '#efead3',
		'--fg': '#1f1f1f', // foreground
		'--muted': '#6c664b', // comment
		'--border-color': '#dcd7c0',
		'--accent': '#644ac9', // purple
		'--accent-fg': '#fffbeb',
		'--success': '#14710a', // green
		'--success-fg': '#fffbeb',
		'--warn': '#846e15', // yellow
		'--warn-fg': '#fffbeb',
		'--danger': '#cb3a2a', // red
		'--danger-fg': '#fffbeb',
		'--info': '#036a96', // cyan
		'--info-fg': '#fffbeb',
		'--overlay': 'rgba(31, 31, 31, 0.28)'
	}
} satisfies ColorTheme;
