import type { ConceptTheme } from '../types';

// Aero — glossy "frutiger" glass à la Windows Vista/7. Heavy blur, bright top
// light edge, layered drop shadows, pill rounding, springy motion.
export default {
	id: 'aero',
	name: 'Aero',
	tokens: {
		'--radius-sm': '8px',
		'--radius-md': '14px',
		'--radius-lg': '22px',
		'--radius-full': '9999px',
		'--border-width': '1px',
		'--shadow-sm':
			'inset 0 1px 0 rgba(255,255,255,0.4), 0 2px 6px rgba(0,0,0,0.25)',
		'--shadow-md':
			'inset 0 1px 0 rgba(255,255,255,0.45), 0 6px 18px rgba(0,0,0,0.3)',
		'--shadow-lg':
			'inset 0 1px 0 rgba(255,255,255,0.5), 0 14px 40px rgba(0,0,0,0.36)',
		'--blur': '18px',
		'--surface-alpha': '0.62',
		'--depth': '2',
		'--motion-fast': '120ms',
		'--motion-base': '240ms',
		'--motion-ease': 'cubic-bezier(0.34, 1.4, 0.64, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '700',
		'--space-1': '5px',
		'--space-2': '9px',
		'--space-3': '15px',
		'--space-4': '21px',
		'--space-5': '30px',
		'--space-6': '42px',
		'--border-color': 'rgba(255,255,255,0.35)'
	}
} satisfies ConceptTheme;
