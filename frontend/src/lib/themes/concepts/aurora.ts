import type { ConceptTheme } from '../types';

// Aurora — soft colored glow shadows keyed to the accent, generous rounding,
// gentle blur. Surfaces feel like they emit a faint light. Palette-aware: the
// glow is built from --accent so it matches whatever color theme is active.
export default {
	id: 'aurora',
	name: 'Aurora',
	tokens: {
		'--radius-sm': '12px',
		'--radius-md': '20px',
		'--radius-lg': '30px',
		'--radius-full': '9999px',
		'--border-width': '1px',
		'--shadow-sm': '0 2px 10px color-mix(in srgb, var(--accent) 30%, transparent)',
		'--shadow-md': '0 6px 24px color-mix(in srgb, var(--accent) 36%, transparent)',
		'--shadow-lg': '0 14px 48px color-mix(in srgb, var(--accent) 44%, transparent)',
		'--blur': '8px',
		'--surface-alpha': '0.8',
		'--depth': '2',
		'--motion-fast': '140ms',
		'--motion-base': '280ms',
		'--motion-ease': 'cubic-bezier(0.16, 1, 0.3, 1)',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '5px',
		'--space-2': '9px',
		'--space-3': '15px',
		'--space-4': '22px',
		'--space-5': '32px',
		'--space-6': '46px',
		'--border-color': 'color-mix(in srgb, var(--accent) 24%, transparent)'
	}
} satisfies ConceptTheme;
