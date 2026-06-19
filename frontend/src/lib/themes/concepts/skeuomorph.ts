import type { ConceptTheme } from '../types';

// Tactile, inset/emboss feel with layered bevels. Moderate rounding.
export default {
	id: 'skeuomorph',
	name: 'Skeuomorph',
	tokens: {
		'--radius-sm': '6px',
		'--radius-md': '9px',
		'--radius-lg': '14px',
		'--radius-full': '9999px',
		'--border-width': '1px',
		'--shadow-sm':
			'inset 0 1px 0 rgba(255,255,255,0.25), 0 1px 2px rgba(0,0,0,0.35)',
		'--shadow-md':
			'inset 0 1px 0 rgba(255,255,255,0.3), 0 3px 6px rgba(0,0,0,0.4)',
		'--shadow-lg':
			'inset 0 2px 0 rgba(255,255,255,0.3), 0 8px 16px rgba(0,0,0,0.45)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '2',
		'--motion-fast': '100ms',
		'--motion-base': '180ms',
		'--motion-ease': 'cubic-bezier(0.4, 0, 0.2, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '700',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '18px',
		'--space-5': '26px',
		'--space-6': '36px',
		// interaction
		'--shadow-hover': '0 6px 14px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.25)',
		'--hover-lift': '-1px',
		'--hover-glow': '0 0 0 0 transparent',
		'--focus-ring': '0 0 0 3px color-mix(in srgb, var(--accent) 45%, transparent)',
		'--press-scale': '0.98',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	defaultFont: 'merriweather'
} satisfies ConceptTheme;
