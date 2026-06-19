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
		'--border-color': 'rgba(255,255,255,0.18)',
		// interaction
		'--shadow-hover': '0 14px 40px rgba(0,0,0,0.38)',
		'--hover-lift': '-2px',
		'--hover-glow': '0 0 30px color-mix(in srgb, var(--accent) 35%, transparent)',
		'--focus-ring': '0 0 0 3px color-mix(in srgb, var(--accent) 50%, transparent)',
		'--press-scale': '0.98',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	effects: [{"kind":"aurora","opacity":0.3,"speed":0.6}],
	defaultFont: 'plus-jakarta-sans'
} satisfies ConceptTheme;
