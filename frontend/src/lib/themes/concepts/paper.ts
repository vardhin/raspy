import type { ConceptTheme } from '../types';

// Paper — flat, tactile, print-like. Hairline borders, very subtle ink-toned
// shadow, modest rounding, calm motion. No blur, fully opaque.
export default {
	id: 'paper',
	name: 'Paper',
	tokens: {
		'--radius-sm': '3px',
		'--radius-md': '5px',
		'--radius-lg': '8px',
		'--radius-full': '9999px',
		'--border-width': '1px',
		'--shadow-sm': '0 1px 2px rgba(0,0,0,0.08)',
		'--shadow-md': '0 1px 3px rgba(0,0,0,0.1), 0 2px 6px rgba(0,0,0,0.06)',
		'--shadow-lg': '0 2px 5px rgba(0,0,0,0.1), 0 6px 16px rgba(0,0,0,0.08)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '1',
		'--motion-fast': '120ms',
		'--motion-base': '200ms',
		'--motion-ease': 'ease-out',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '14px',
		'--space-4': '20px',
		'--space-5': '28px',
		'--space-6': '40px',
		// interaction
		'--shadow-hover': '0 3px 10px rgba(0,0,0,0.14)',
		'--hover-lift': '-1px',
		'--hover-glow': '0 0 0 0 transparent',
		'--focus-ring': '0 0 0 2px color-mix(in srgb, var(--accent) 55%, transparent)',
		'--press-scale': '0.99',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)',
		'--fg-accent': 'var(--fg)'
	},
	defaultFont: 'lora'
} satisfies ConceptTheme;
