import type { ConceptTheme } from '../types';

// Wireframe — lo-fi blueprint look. Dashed hairline borders, no fill, no
// shadow, instant motion. Like a sketch/prototype mockup. Borders keyed to
// --muted so they stay legible on any palette.
export default {
	id: 'wireframe',
	name: 'Wireframe',
	tokens: {
		'--radius-sm': '2px',
		'--radius-md': '4px',
		'--radius-lg': '6px',
		'--radius-full': '9999px',
		'--border-width': '1.5px',
		// dashed effect is structural (set in app.css for data-concept="wireframe")
		'--shadow-sm': 'none',
		'--shadow-md': 'none',
		'--shadow-lg': 'none',
		'--blur': '0px',
		'--surface-alpha': '0',
		'--depth': '0',
		'--motion-fast': '40ms',
		'--motion-base': '80ms',
		'--motion-ease': 'linear',
		'--font-weight-normal': '400',
		'--font-weight-bold': '600',
		'--space-1': '4px',
		'--space-2': '8px',
		'--space-3': '12px',
		'--space-4': '18px',
		'--space-5': '26px',
		'--space-6': '36px',
		'--border-color': 'var(--muted)'
	}
} satisfies ConceptTheme;
