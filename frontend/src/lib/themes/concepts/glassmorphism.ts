import type { ConceptTheme } from '../types';

// Semi-transparent surfaces + backdrop blur + soft glow. Pairs with any palette;
// surfaces let the bg hue bleed through via --surface-alpha < 1.
export default {
	id: 'glassmorphism',
	name: 'Glassmorphism',
	tokens: {
		'--radius-sm': '10px',
		'--radius-md': '16px',
		'--radius-lg': '24px',
		'--radius-full': '9999px',
		'--border-width': '1px',
		'--shadow-sm': '0 2px 8px rgba(0,0,0,0.18)',
		'--shadow-md': '0 8px 24px rgba(0,0,0,0.28)',
		'--shadow-lg': '0 16px 48px rgba(0,0,0,0.36)',
		'--blur': '14px',
		'--surface-alpha': '0.55',
		'--depth': '1',
		'--motion-fast': '120ms',
		'--motion-base': '240ms',
		'--motion-ease': 'cubic-bezier(0.4, 0, 0.2, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '14px',
		'--space-4': '20px',
		'--space-5': '28px',
		'--space-6': '40px',
		// glass reads borders as a faint light edge
		'--border-color': 'rgba(255,255,255,0.18)'
	}
} satisfies ConceptTheme;
