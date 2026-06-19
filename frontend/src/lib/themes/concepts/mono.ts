import type { ConceptTheme } from '../types';

// Mono — terminal × brutalist hybrid: monospace (applied in app.css for
// data-concept="mono"), sharp small radius, thick 2px palette-aware borders,
// crisp offset shadow, snappy motion. Heavier weight than plain Terminal.
export default {
	id: 'mono',
	name: 'Mono',
	tokens: {
		'--radius-sm': '0px',
		'--radius-md': '2px',
		'--radius-lg': '4px',
		'--radius-full': '0px',
		'--border-width': '2px',
		'--shadow-sm': '2px 2px 0 var(--border-color)',
		'--shadow-md': '3px 3px 0 var(--border-color)',
		'--shadow-lg': '5px 5px 0 var(--border-color)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '0',
		'--motion-fast': '50ms',
		'--motion-base': '90ms',
		'--motion-ease': 'cubic-bezier(0.2, 0, 0, 1)',
		'--font-weight-normal': '500',
		'--font-weight-bold': '700',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '16px',
		'--space-5': '22px',
		'--space-6': '32px',
		'--border-color': 'color-mix(in srgb, var(--fg) 65%, var(--border-color))',
		// interaction
		'--shadow-hover': '0 0 0 0 transparent',
		'--hover-lift': '0',
		'--hover-glow': '0 0 0 0 transparent',
		'--focus-ring': '0 0 0 2px var(--fg)',
		'--press-scale': '1',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)',
		'--fg-accent': 'var(--fg)'
	},
	defaultFont: 'space-mono'
} satisfies ConceptTheme;
