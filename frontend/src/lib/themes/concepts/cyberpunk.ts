import type { ConceptTheme } from '../types';

// Cyberpunk — neon-edged HUD. Sharp corners, glowing accent borders + outer
// glow shadows, near-opaque dark surfaces, fast motion. Glow built from
// --accent so it tracks the active palette.
export default {
	id: 'cyberpunk',
	name: 'Cyberpunk',
	tokens: {
		'--radius-sm': '0px',
		'--radius-md': '2px',
		'--radius-lg': '4px',
		'--radius-full': '0px',
		'--border-width': '1.5px',
		'--shadow-sm':
			'0 0 6px color-mix(in srgb, var(--accent) 60%, transparent)',
		'--shadow-md':
			'0 0 12px color-mix(in srgb, var(--accent) 60%, transparent), 0 0 2px var(--accent)',
		'--shadow-lg':
			'0 0 24px color-mix(in srgb, var(--accent) 70%, transparent), 0 0 4px var(--accent)',
		'--blur': '2px',
		'--surface-alpha': '0.92',
		'--depth': '1',
		'--motion-fast': '60ms',
		'--motion-base': '120ms',
		'--motion-ease': 'cubic-bezier(0.2, 0, 0, 1)',
		'--font-weight-normal': '500',
		'--font-weight-bold': '700',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '13px',
		'--space-4': '19px',
		'--space-5': '27px',
		'--space-6': '38px',
		'--border-color': 'color-mix(in srgb, var(--accent) 70%, transparent)',
		// interaction
		'--shadow-hover': '0 0 20px color-mix(in srgb, var(--accent) 70%, transparent)',
		'--hover-lift': '0',
		'--hover-glow': '0 0 12px color-mix(in srgb, var(--accent) 80%, transparent), inset 0 0 8px color-mix(in srgb, var(--accent) 30%, transparent)',
		'--focus-ring': '0 0 0 2px var(--accent), 0 0 14px color-mix(in srgb, var(--accent) 70%, transparent)',
		'--press-scale': '0.99',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)',
		'--fg-accent': 'color-mix(in srgb, var(--fg) 55%, var(--accent))'
	},
	effects: [{"kind":"scanlines","opacity":0.25},{"kind":"grid","opacity":0.18,"speed":0.5}],
	defaultFont: 'orbitron'
} satisfies ConceptTheme;
