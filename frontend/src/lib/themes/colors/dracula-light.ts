import type { ColorTheme } from '../types';

// Alucard — the official light counterpart of Dracula.
// https://draculatheme.com/alucard
export default {
	id: 'dracula-light',
	name: 'Dracula (Light)',
	mode: 'light',
	tokens: {
		'--bg': '#f8f8f2',
		'--surface': '#ffffff',
		'--surface-2': '#ececed',
		'--fg': '#1f1f1f',
		'--muted': '#6c664b',
		'--border-color': '#cfcfc2',
		'--accent': '#7544c0',
		'--accent-fg': '#ffffff',
		'--success': '#14710a',
		'--success-fg': '#ffffff',
		'--warn': '#846e15',
		'--warn-fg': '#ffffff',
		'--danger': '#cb3a2a',
		'--danger-fg': '#ffffff',
		'--info': '#036a96',
		'--info-fg': '#ffffff',
		'--overlay': 'rgba(31, 31, 31, 0.35)'
	}
} satisfies ColorTheme;
