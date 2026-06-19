import type { ConceptTheme } from '../types';

// Hard edges, thick borders, offset solid shadows, no blur, snappy motion.
// Border + shadow keyed to --fg so it stays correct in any palette.
export default {
	id: 'neobrutalism',
	name: 'Neobrutalism',
	tokens: {
		'--radius-sm': '0px',
		'--radius-md': '0px',
		'--radius-lg': '2px',
		'--radius-full': '0px',
		'--border-width': '3px',
		'--shadow-sm': '3px 3px 0 var(--fg)',
		'--shadow-md': '5px 5px 0 var(--fg)',
		'--shadow-lg': '8px 8px 0 var(--fg)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '0',
		'--motion-fast': '60ms',
		'--motion-base': '90ms',
		'--motion-ease': 'cubic-bezier(0.2, 0, 0, 1)',
		'--font-weight-normal': '500',
		'--font-weight-bold': '800',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '18px',
		'--space-5': '26px',
		'--space-6': '36px',
		// pure, palette-aware hard border
		'--border-color': 'var(--fg)',
		// interaction
		'--shadow-hover': '7px 7px 0 var(--fg)',
		'--hover-lift': '0',
		'--hover-glow': '0 0 0 0 transparent',
		'--focus-ring': '0 0 0 3px var(--accent), 5px 5px 0 var(--fg)',
		'--press-scale': '1',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)',
		'--fg-accent': 'var(--fg)'
	},
	defaultFont: 'space-grotesk'
} satisfies ConceptTheme;
