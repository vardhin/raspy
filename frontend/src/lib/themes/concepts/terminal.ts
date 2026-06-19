import type { ConceptTheme } from '../types';

// Sharp, monospace, minimal. Single-cell borders, zero radius, instant motion.
// (Concepts can't set font-family via tokens alone; the shell applies a mono
// stack when data-concept="terminal" — see app.css.)
export default {
	id: 'terminal',
	name: 'Terminal',
	tokens: {
		'--radius-sm': '0px',
		'--radius-md': '0px',
		'--radius-lg': '0px',
		'--radius-full': '0px',
		'--border-width': '1px',
		'--shadow-sm': 'none',
		'--shadow-md': 'none',
		'--shadow-lg': 'none',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '0',
		'--motion-fast': '0ms',
		'--motion-base': '0ms',
		'--motion-ease': 'linear',
		'--font-weight-normal': '400',
		'--font-weight-bold': '700',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '16px',
		'--space-5': '20px',
		'--space-6': '28px',
		// interaction
		'--shadow-hover': '0 0 14px color-mix(in srgb, var(--accent) 50%, transparent)',
		'--hover-lift': '0',
		'--hover-glow': '0 0 8px color-mix(in srgb, var(--accent) 50%, transparent)',
		'--focus-ring': '0 0 0 2px var(--accent)',
		'--press-scale': '1',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)',
		'--fg-accent': 'var(--accent)'
	},
	effects: [{"kind":"scanlines","opacity":0.18}],
	defaultFont: 'jetbrains-mono'
} satisfies ConceptTheme;
