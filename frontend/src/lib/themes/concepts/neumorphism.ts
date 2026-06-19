import type { ConceptTheme } from '../types';

// Neumorphism — soft UI. Surfaces share the background hue and are defined by a
// dual light/dark shadow pair (extruded look). Borderless, medium rounding.
// The dual shadows use neutral light/dark so the effect reads on any palette.
export default {
	id: 'neumorphism',
	name: 'Neumorphism',
	tokens: {
		'--radius-sm': '10px',
		'--radius-md': '18px',
		'--radius-lg': '28px',
		'--radius-full': '9999px',
		'--border-width': '0px',
		'--shadow-sm':
			'4px 4px 8px rgba(0,0,0,0.35), -4px -4px 8px rgba(255,255,255,0.06)',
		'--shadow-md':
			'7px 7px 14px rgba(0,0,0,0.4), -7px -7px 14px rgba(255,255,255,0.07)',
		'--shadow-lg':
			'12px 12px 24px rgba(0,0,0,0.45), -12px -12px 24px rgba(255,255,255,0.08)',
		'--blur': '0px',
		'--surface-alpha': '1',
		'--depth': '2',
		'--motion-fast': '120ms',
		'--motion-base': '220ms',
		'--motion-ease': 'cubic-bezier(0.4, 0, 0.2, 1)',
		'--font-weight-normal': '500',
		'--font-weight-bold': '700',
		'--space-1': '5px',
		'--space-2': '10px',
		'--space-3': '16px',
		'--space-4': '22px',
		'--space-5': '32px',
		'--space-6': '44px',
		// surfaces blend toward the page bg so the extrusion reads as one material
		'--surface': 'color-mix(in srgb, var(--bg) 92%, var(--fg))',
		'--surface-2': 'var(--bg)',
		'--border-color': 'transparent',
		// interaction
		'--shadow-hover': 'inset 2px 2px 6px rgba(0,0,0,0.22), inset -2px -2px 6px rgba(255,255,255,0.06)',
		'--hover-lift': '0',
		'--hover-glow': '0 0 0 0 transparent',
		'--focus-ring': '0 0 0 2px color-mix(in srgb, var(--accent) 50%, transparent)',
		'--press-scale': '0.99',
		'--transition': 'background var(--motion-base) var(--motion-ease), color var(--motion-base) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease)'
	},
	defaultFont: 'manrope'
} satisfies ConceptTheme;
