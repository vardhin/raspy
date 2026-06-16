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
		'--border-color': 'color-mix(in srgb, var(--accent) 70%, transparent)'
	}
} satisfies ConceptTheme;
