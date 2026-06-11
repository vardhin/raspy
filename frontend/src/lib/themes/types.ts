// The theme token contract. See plan/45-theming.md §3.
//
// Two orthogonal axes:
//   - ColorTheme sets HUE tokens (what color a surface is).
//   - ConceptTheme sets FORM tokens (what a surface IS: radius, shadow, blur…).
//
// Components read ONLY these tokens (never raw values), so any color × any concept
// composes. Token values may reference other tokens, e.g. 'var(--fg)'.

/** Hue / palette tokens — owned by color themes. */
export interface ColorTokens {
	'--bg': string;
	'--surface': string;
	'--surface-2': string;
	'--fg': string;
	'--muted': string;
	'--border-color': string;
	'--accent': string;
	'--accent-fg': string;
	'--success': string;
	'--success-fg': string;
	'--warn': string;
	'--warn-fg': string;
	'--danger': string;
	'--danger-fg': string;
	'--info': string;
	'--info-fg': string;
	'--overlay': string;
}

/** Form / material tokens — owned by concept themes. */
export interface ConceptTokens {
	'--radius-sm': string;
	'--radius-md': string;
	'--radius-lg': string;
	'--radius-full': string;
	'--border-width': string;
	'--shadow-sm': string;
	'--shadow-md': string;
	'--shadow-lg': string;
	'--blur': string;
	'--surface-alpha': string;
	'--depth': string;
	'--motion-fast': string;
	'--motion-base': string;
	'--motion-ease': string;
	'--font-weight-normal': string;
	'--font-weight-bold': string;
	'--space-1': string;
	'--space-2': string;
	'--space-3': string;
	'--space-4': string;
	'--space-5': string;
	'--space-6': string;
}

/**
 * A concept MAY override a color token (e.g. neobrutalism forcing
 * `--border-color: var(--fg)`), expressed relative to color tokens so it still
 * respects the active palette. Hence concept tokens are a partial color overlay too.
 */
export type ConceptTokenMap = ConceptTokens & Partial<ColorTokens>;

export interface ColorTheme {
	id: string;
	name: string;
	/** 'dark' | 'light' — used to pick a sensible default & for UI hints. */
	mode: 'dark' | 'light';
	tokens: ColorTokens;
}

export interface ConceptTheme {
	id: string;
	name: string;
	tokens: ConceptTokenMap;
}

/** The persisted selection: just two ids, never the definitions. */
export interface ThemeChoice {
	color: string;
	concept: string;
}
