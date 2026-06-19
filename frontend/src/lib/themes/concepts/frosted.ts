import type { ConceptTheme } from '../types';

// Heavier blur, lighter alpha than glassmorphism — a thick frosted pane look.
export default {
	id: 'frosted',
	name: 'Frosted Glass',
	tokens: {
		'--radius-sm': '12px',
		'--radius-md': '20px',
		'--radius-lg': '28px',
		'--radius-full': '9999px',
		'--border-width': '1px',
		'--shadow-sm': '0 2px 10px rgba(0,0,0,0.14)',
		'--shadow-md': '0 10px 30px rgba(0,0,0,0.22)',
		'--shadow-lg': '0 20px 60px rgba(0,0,0,0.3)',
		'--blur': '28px',
		'--surface-alpha': '0.4',
		'--depth': '1',
		'--motion-fast': '130ms',
		'--motion-base': '260ms',
		'--motion-ease': 'cubic-bezier(0.4, 0, 0.2, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '14px',
		'--space-4': '22px',
		'--space-5': '30px',
		'--space-6': '44px',
		'--border-color': 'rgba(255,255,255,0.22)',
		// interaction
		'--shadow-hover': '0 12px 36px rgba(0,0,0,0.30)',
		'--hover-lift': '-2px',
		'--hover-glow': '0 0 28px color-mix(in srgb, var(--accent) 30%, transparent)',
		'--focus-ring': '0 0 0 3px color-mix(in srgb, var(--accent) 45%, transparent)',
		'--press-scale': '0.98',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	effects: [{"kind":"breathe","opacity":0.25}],
	defaultFont: 'dm-sans'
} satisfies ConceptTheme;
