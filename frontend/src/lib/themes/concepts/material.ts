import type { ConceptTheme } from '../types';

// Material-style elevation: tiered ambient + key light shadows, modest rounding.
export default {
	id: 'material',
	name: 'Material',
	tokens: {
		'--radius-sm': '4px',
		'--radius-md': '8px',
		'--radius-lg': '16px',
		'--radius-full': '9999px',
		'--border-width': '0px',
		'--shadow-sm': '0 1px 3px rgba(0,0,0,0.2), 0 1px 2px rgba(0,0,0,0.24)',
		'--shadow-md': '0 3px 6px rgba(0,0,0,0.22), 0 3px 6px rgba(0,0,0,0.26)',
		'--shadow-lg': '0 10px 20px rgba(0,0,0,0.24), 0 6px 6px rgba(0,0,0,0.28)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '1',
		'--motion-fast': '100ms',
		'--motion-base': '200ms',
		'--motion-ease': 'cubic-bezier(0.4, 0, 0.2, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '500',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '16px',
		'--space-5': '24px',
		'--space-6': '32px'
	}
} satisfies ConceptTheme;
