import type { ConceptTheme } from '../types';

// Plush — soft, generous, expensive-feeling. Large rounding, no border, big
// diffuse layered shadows, slow luxurious motion, roomy spacing.
export default {
	id: 'plush',
	name: 'Plush',
	tokens: {
		'--radius-sm': '12px',
		'--radius-md': '20px',
		'--radius-lg': '32px',
		'--radius-full': '9999px',
		'--border-width': '0px',
		'--shadow-sm': '0 4px 16px rgba(0,0,0,0.1)',
		'--shadow-md': '0 10px 32px rgba(0,0,0,0.14), 0 2px 8px rgba(0,0,0,0.08)',
		'--shadow-lg': '0 24px 64px rgba(0,0,0,0.18), 0 6px 18px rgba(0,0,0,0.1)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '3',
		'--motion-fast': '180ms',
		'--motion-base': '360ms',
		'--motion-ease': 'cubic-bezier(0.22, 1, 0.36, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '6px',
		'--space-2': '12px',
		'--space-3': '18px',
		'--space-4': '26px',
		'--space-5': '38px',
		'--space-6': '54px',
		'--border-color': 'transparent'
	}
} satisfies ConceptTheme;
