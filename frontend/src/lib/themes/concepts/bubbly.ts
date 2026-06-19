import type { ConceptTheme } from '../types';

// Bubbly — playful, maximally rounded, bouncy. Big radii, no borders, soft
// drop shadows, overshooting spring motion, slightly looser spacing.
export default {
	id: 'bubbly',
	name: 'Bubbly',
	tokens: {
		'--radius-sm': '16px',
		'--radius-md': '26px',
		'--radius-lg': '40px',
		'--radius-full': '9999px',
		'--border-width': '0px',
		'--shadow-sm': '0 4px 10px rgba(0,0,0,0.12)',
		'--shadow-md': '0 8px 22px rgba(0,0,0,0.16)',
		'--shadow-lg': '0 16px 40px rgba(0,0,0,0.2)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '2',
		'--motion-fast': '160ms',
		'--motion-base': '320ms',
		'--motion-ease': 'cubic-bezier(0.34, 1.7, 0.5, 1)',
		'--font-weight-normal': '500',
		'--font-weight-bold': '800',
		'--space-1': '6px',
		'--space-2': '11px',
		'--space-3': '17px',
		'--space-4': '24px',
		'--space-5': '34px',
		'--space-6': '48px',
		'--border-color': 'transparent',
		// interaction
		'--shadow-hover': '0 12px 28px rgba(0,0,0,0.22)',
		'--hover-lift': '-3px',
		'--hover-glow': '0 0 0 4px color-mix(in srgb, var(--accent) 22%, transparent)',
		'--focus-ring': '0 0 0 4px color-mix(in srgb, var(--accent) 45%, transparent)',
		'--press-scale': '0.94',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	defaultFont: 'nunito'
} satisfies ConceptTheme;
