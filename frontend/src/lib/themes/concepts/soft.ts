import type { ConceptTheme } from '../types';

// Gentle elevation + generous rounding. The "friendly default".
export default {
	id: 'soft',
	name: 'Soft',
	tokens: {
		'--radius-sm': '8px',
		'--radius-md': '12px',
		'--radius-lg': '18px',
		'--radius-full': '9999px',
		'--border-width': '1px',
		'--shadow-sm': '0 1px 2px rgba(0,0,0,0.12)',
		'--shadow-md': '0 4px 12px rgba(0,0,0,0.16)',
		'--shadow-lg': '0 12px 32px rgba(0,0,0,0.22)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '1',
		'--motion-fast': '120ms',
		'--motion-base': '220ms',
		'--motion-ease': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '14px',
		'--space-4': '20px',
		'--space-5': '28px',
		'--space-6': '40px',
		// interaction
		'--shadow-hover': '0 8px 22px rgba(0,0,0,0.20)',
		'--hover-lift': '-2px',
		'--hover-glow': '0 0 0 4px color-mix(in srgb, var(--accent) 12%, transparent)',
		'--focus-ring': '0 0 0 3px color-mix(in srgb, var(--accent) 40%, transparent)',
		'--press-scale': '0.97',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	defaultFont: 'inter'
} satisfies ConceptTheme;
