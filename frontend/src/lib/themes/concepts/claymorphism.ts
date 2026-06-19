import type { ConceptTheme } from '../types';

// Puffy, rounded, soft double-shadow (outer drop + inner light) for a clay look.
export default {
	id: 'claymorphism',
	name: 'Claymorphism',
	tokens: {
		'--radius-sm': '14px',
		'--radius-md': '22px',
		'--radius-lg': '34px',
		'--radius-full': '9999px',
		'--border-width': '0px',
		'--shadow-sm':
			'0 6px 12px rgba(0,0,0,0.18), inset 0 2px 4px rgba(255,255,255,0.25), inset 0 -3px 6px rgba(0,0,0,0.18)',
		'--shadow-md':
			'0 12px 24px rgba(0,0,0,0.22), inset 0 3px 6px rgba(255,255,255,0.28), inset 0 -4px 8px rgba(0,0,0,0.22)',
		'--shadow-lg':
			'0 20px 40px rgba(0,0,0,0.26), inset 0 4px 8px rgba(255,255,255,0.3), inset 0 -6px 12px rgba(0,0,0,0.24)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '2',
		'--motion-fast': '140ms',
		'--motion-base': '260ms',
		'--motion-ease': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
		'--font-weight-normal': '500',
		'--font-weight-bold': '700',
		'--space-1': '6px',
		'--space-2': '10px',
		'--space-3': '16px',
		'--space-4': '22px',
		'--space-5': '32px',
		'--space-6': '44px',
		// interaction
		'--shadow-hover': '0 14px 34px rgba(0,0,0,0.20)',
		'--hover-lift': '-3px',
		'--hover-glow': '0 0 0 0 transparent',
		'--focus-ring': '0 0 0 3px color-mix(in srgb, var(--accent) 40%, transparent)',
		'--press-scale': '0.97',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	defaultFont: 'poppins'
} satisfies ConceptTheme;
