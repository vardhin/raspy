import type { ConceptTheme } from '../types';

// Pixel — retro 8-bit. Zero radius, chunky 2px borders, hard 1-step pixel
// shadows, stepped (no-ease) motion, monospace (applied in app.css for
// data-concept="pixel"). Border keyed to --fg so it reads on any palette.
export default {
	id: 'pixel',
	name: 'Pixel',
	tokens: {
		'--radius-sm': '0px',
		'--radius-md': '0px',
		'--radius-lg': '0px',
		'--radius-full': '0px',
		'--border-width': '2px',
		'--shadow-sm': '2px 2px 0 var(--border-color)',
		'--shadow-md': '4px 4px 0 var(--border-color)',
		'--shadow-lg': '6px 6px 0 var(--border-color)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '0',
		'--motion-fast': '0ms',
		'--motion-base': '0ms',
		'--motion-ease': 'steps(2, end)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '700',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '16px',
		'--space-5': '24px',
		'--space-6': '32px',
		'--border-color': 'var(--fg)',
		// interaction
		'--shadow-hover': '4px 4px 0 var(--fg)',
		'--hover-lift': '0',
		'--hover-glow': '0 0 0 0 transparent',
		'--focus-ring': '0 0 0 2px var(--accent)',
		'--press-scale': '1',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	effects: [{"kind":"scanlines","opacity":0.15}],
	defaultFont: 'space-mono'
} satisfies ConceptTheme;
