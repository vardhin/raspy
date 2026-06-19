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
	/** Accent-tinted foreground for titles/headings. Defaults to var(--fg);
	 *  concepts may bleed more accent in via the ConceptTokenMap overlay. */
	'--fg-accent': string;
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
	// --- Interaction tokens: how surfaces respond to hover / focus / press. ---
	// Read uniformly by interactive components so each concept defines its own
	// in-character feedback (aurora glows, neobrutalism shifts, flat stays subtle).
	/** Shadow applied on hover (usually a stronger / glowier --shadow-md). */
	'--shadow-hover': string;
	/** translateY applied on hover, e.g. '-2px' or '0' for concepts that don't lift. */
	'--hover-lift': string;
	/** Extra glow ring on hover, layered after --shadow-hover (may be 'none'). */
	'--hover-glow': string;
	/** box-shadow used for :focus-visible (the focus ring). */
	'--focus-ring': string;
	/** scale() applied on :active, e.g. '0.97' or '1' for none. */
	'--press-scale': string;
	/** Shared transition shorthand so theme switches & interactions morph smoothly. */
	'--transition': string;
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

/**
 * An animated background effect a concept can opt into. Rendered by the single
 * <ThemeEffects> layer in the app shell (fixed, full-viewport, pointer-events:none).
 * All are CSS-driven and keyed to the active palette (via --accent) so they match
 * whatever color theme is live. Off when the user disables animations or the OS
 * requests reduced motion.
 */
export type EffectSpec =
	/** Drifting aurora-borealis gradients keyed to the accent. */
	| { kind: 'aurora'; opacity?: number; speed?: number }
	/** Slow scale/opacity pulse on the whole backdrop. */
	| { kind: 'breathe'; opacity?: number; speed?: number }
	/** A glow that orbits the viewport. */
	| { kind: 'orbit'; opacity?: number; speed?: number }
	/** CRT-style horizontal scanlines. */
	| { kind: 'scanlines'; opacity?: number }
	/** Retro perspective / flat grid. */
	| { kind: 'grid'; opacity?: number; speed?: number }
	/** Subtle film grain. */
	| { kind: 'noise'; opacity?: number };

export interface ConceptTheme {
	id: string;
	name: string;
	tokens: ConceptTokenMap;
	/** Animated background layers this concept renders. Optional. */
	effects?: EffectSpec[];
	/** Default font id (from the fonts registry) suiting this concept. Optional;
	 *  falls back to the global default when absent. */
	defaultFont?: string;
}

/**
 * The persisted selection. `font` is the only non-id state:
 *   - null  → follow the active concept's defaultFont (also the "reset" state).
 *   - <id>  → a pinned font that survives concept changes until changed again.
 */
export interface ThemeChoice {
	color: string;
	concept: string;
	font: string | null;
	animations: boolean;
}
