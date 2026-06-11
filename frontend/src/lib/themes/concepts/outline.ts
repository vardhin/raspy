import type { ConceptTheme } from '../types';

// Border-led, minimal fill. Surfaces are nearly transparent; structure is
// communicated by outlines, not shadows or fills.
export default {
	id: 'outline',
	name: 'Outline',
	tokens: {
		'--radius-sm': '6px',
		'--radius-md': '10px',
		'--radius-lg': '16px',
		'--radius-full': '9999px',
		'--border-width': '1.5px',
		'--shadow-sm': 'none',
		'--shadow-md': 'none',
		'--shadow-lg': 'none',
		'--blur': '0px',
		'--surface-alpha': '0',
		'--depth': '0',
		'--motion-fast': '90ms',
		'--motion-base': '160ms',
		'--motion-ease': 'cubic-bezier(0.4, 0, 0.2, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '18px',
		'--space-5': '26px',
		'--space-6': '36px'
	}
} satisfies ConceptTheme;
