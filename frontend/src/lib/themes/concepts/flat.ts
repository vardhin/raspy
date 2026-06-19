import type { ConceptTheme } from '../types';

// Baseline concept: no blur, no shadow, opaque surfaces, modest rounding.
// Every other concept is a deviation from this.
export default {
	id: 'flat',
	name: 'Flat',
	tokens: {
		'--radius-sm': '4px',
		'--radius-md': '6px',
		'--radius-lg': '10px',
		'--radius-full': '9999px',
		'--border-width': '1px',
		'--shadow-sm': 'none',
		'--shadow-md': 'none',
		'--shadow-lg': 'none',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '0',
		'--motion-fast': '90ms',
		'--motion-base': '160ms',
		'--motion-ease': 'cubic-bezier(0.4, 0, 0.2, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '16px',
		'--space-5': '24px',
		'--space-6': '32px',
		// interaction
		'--shadow-hover': '0 0 0 0 transparent',
		'--hover-lift': '0',
		'--hover-glow': '0 0 0 0 transparent',
		'--focus-ring': '0 0 0 2px var(--accent)',
		'--press-scale': '0.99',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	defaultFont: 'work-sans'
} satisfies ConceptTheme;
