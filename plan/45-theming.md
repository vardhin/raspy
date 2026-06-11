# Theming & Component System

Two orthogonal theme axes that compose freely, a tiny set of versatile components,
and a hard rule that makes it all modular: **components only read design tokens,
never raw values.**

## 1. The core idea: token-driven components

Every component styles itself **exclusively** through CSS custom properties (design
tokens) on `:root`. A component never hardcodes a color, radius, shadow, or blur.

```css
/* a Button never does this */     background: #bd93f9;  border-radius: 8px;
/* it does this */                 background: var(--accent);  border-radius: var(--radius-md);
```

Because every visual decision routes through a token, **swapping the token values
re-skins the entire app** — no component changes, ever. Themes are just sets of
token values.

## 2. Two axes (fully orthogonal)

Tokens split into two groups, owned by two independent theme types:

| Axis | Owns these tokens | Examples | Lives in |
|---|---|---|---|
| **Color theme** | hue/palette: `--bg`, `--surface`, `--fg`, `--muted`, `--accent`, `--success`, `--warn`, `--danger`, semantic ramps | Dracula, Gruvbox, Nord, Catppuccin, Solarized, Tokyo Night… | `src/lib/themes/colors/` |
| **Concept theme** | form/material: `--radius-*`, `--shadow-*`, `--border-*`, `--blur`, `--surface-alpha`, `--depth`, `--motion-*`, `--font-weight-*` | Flat, Glassmorphism, Neobrutalism, Claymorphism, Frosted, Skeuomorph… | `src/lib/themes/concepts/` |

You pick **one color + one concept**. `Gruvbox × Neobrutalism` and
`Dracula × Glassmorphism` are both valid. ~15 colors × ~10 concepts = ~150 looks
from ~25 small data files.

### Why this split works

- A color theme answers *"what hue is a surface?"* (`--surface: #282a36`).
- A concept theme answers *"what IS a surface?"* — does it have a hard 3px border
  and offset shadow (neobrutalism), or is it semi-transparent + blurred
  (glassmorphism)? It sets `--border-width`, `--shadow-md`, `--blur`,
  `--surface-alpha`, etc. — **without touching hue**.
- A component composing both: `background: color-mix(in srgb, var(--surface)
  calc(var(--surface-alpha) * 100%), transparent); backdrop-filter: blur(var(--blur));
  border: var(--border-width) solid var(--border-color); box-shadow: var(--shadow-md);`
  — and it just works for any color×concept pair.

## 3. The token contract

A fixed, documented set of tokens both axes agree on. This is the *only* coupling
between themes and components. Adding a token is a deliberate, reviewed act (like
adding a component). Starter contract:

```
/* COLOR tokens (set by color themes) */
--bg            page background
--surface       card/panel base color
--surface-2     raised/secondary surface
--fg            primary text
--muted         secondary text
--border-color  border hue
--accent        primary brand/interactive
--accent-fg     text on accent
--success --warn --danger --info  (+ each with a -fg)
--overlay       modal scrim

/* FORM tokens (set by concept themes) */
--radius-sm --radius-md --radius-lg --radius-full
--border-width
--shadow-sm --shadow-md --shadow-lg     (full box-shadow values)
--blur                                   backdrop blur amount (0 for flat concepts)
--surface-alpha                          surface opacity 0..1 (1 = opaque)
--depth                                  elevation multiplier
--motion-fast --motion-base              transition durations
--motion-ease                            easing curve
--font-weight-normal --font-weight-bold
--space-1 … --space-6                    spacing scale (concept may tune density)
```

A concept theme may legitimately leave some color tokens alone and vice-versa —
that's the orthogonality. If a concept needs a hue decision (neobrutalism's pure
black border), it expresses it **relative to color tokens** (e.g.
`--border-color: var(--fg)`) so it still respects the active palette.

## 4. Theme file format (plain data, auto-registering)

Each theme is a tiny TS module exporting a token map. A glob import registers them
all — **drop a file in, it appears in the picker. No other code changes.**

```ts
// src/lib/themes/colors/dracula.ts
import type { ColorTheme } from '../types';
export default {
  id: 'dracula',
  name: 'Dracula',
  tokens: {
    '--bg': '#282a36', '--surface': '#343746', '--surface-2': '#21222c',
    '--fg': '#f8f8f2', '--muted': '#6272a4', '--border-color': '#44475a',
    '--accent': '#bd93f9', '--accent-fg': '#282a36',
    '--success': '#50fa7b', '--warn': '#f1fa8c',
    '--danger': '#ff5555', '--info': '#8be9fd', '--overlay': '#191a21cc',
  },
} satisfies ColorTheme;
```

```ts
// src/lib/themes/concepts/neobrutalism.ts
import type { ConceptTheme } from '../types';
export default {
  id: 'neobrutalism',
  name: 'Neobrutalism',
  tokens: {
    '--radius-sm': '0px', '--radius-md': '0px', '--radius-lg': '0px',
    '--border-width': '3px', '--border-color': 'var(--fg)',
    '--shadow-sm': '3px 3px 0 var(--fg)', '--shadow-md': '5px 5px 0 var(--fg)',
    '--shadow-lg': '8px 8px 0 var(--fg)',
    '--blur': '0px', '--surface-alpha': '1',
    '--font-weight-bold': '800', '--motion-base': '80ms',
  },
} satisfies ConceptTheme;
```

```ts
// src/lib/themes/registry.ts  — auto-discovery
const colorMods   = import.meta.glob('./colors/*.ts',   { eager: true });
const conceptMods = import.meta.glob('./concepts/*.ts', { eager: true });
export const colorThemes   = Object.values(colorMods).map(m => m.default);
export const conceptThemes = Object.values(conceptMods).map(m => m.default);
```

## 5. Runtime: apply, switch, persist

```ts
// src/lib/themes/store.svelte.ts  (sketch)
function applyTheme(color: ColorTheme, concept: ConceptTheme) {
  const root = document.documentElement;
  for (const [k, v] of Object.entries(color.tokens))   root.style.setProperty(k, v);
  for (const [k, v] of Object.entries(concept.tokens)) root.style.setProperty(k, v);
  root.dataset.color = color.id;        // for any concept that keys off color
  root.dataset.concept = concept.id;    // for rare structural CSS hooks
  localStorage.setItem('theme', JSON.stringify({ color: color.id, concept: concept.id }));
}
```

- **No FOUC:** a tiny inline script in `app.html` reads `localStorage.theme` and sets
  `data-color`/`data-concept` + the persisted tokens **before first paint**.
- **Live switch:** the picker calls `applyTheme()`; CSS vars update → whole UI
  re-skins instantly, no reload.
- **Concept-specific structural CSS** (rare) can hook `:root[data-concept="..."]`
  for things tokens can't express (e.g. a pseudo-element texture). Kept to a minimum.
- **Backend never sends themes** — themes are purely a frontend concern. The Pi
  pushes UI *skeleton + wiring* (see [20-attachments.md](20-attachments.md)); the
  shell renders that skeleton using whatever theme is active. Clean separation:
  **backend = what & how-wired; frontend = how-it-looks.** (A future "sync my theme
  choice across devices" can store just the two ids server-side — still not the
  theme definitions.)

## 6. Components: few, versatile, token-only

The renderer's component set ([20-attachments.md](20-attachments.md) §Tier 1) is the
*same* set used everywhere. Principles:

- **Few primitives, many variants via props**, not many components. A `Surface`
  with `level` and `interactive` props covers cards, panels, list rows, modals.
- **Every component reads only tokens.** Enforced by review + a lint rule (no hex /
  rgb / px-radius / px-shadow literals in component `<style>`; spacing via
  `--space-*`). This is what guarantees any theme works on any component.
- **Variants are semantic, not visual:** `<Button variant="danger">` maps to
  `--danger`, never to a literal red — so it's correct in every palette.

### Starter component set (versatile primitives)

| Component | Variants/props | Replaces |
|---|---|---|
| `Surface` | level, interactive, padded | card, panel, row, sheet |
| `Button` | variant(accent/ghost/danger…), size, icon | all buttons |
| `Text` | role(title/body/muted/label), as | headings, paragraphs, labels |
| `Field` | type(text/number/select/checkbox/textarea), label | all form inputs |
| `Stack` / `Row` | gap, align, wrap | layout (flex) |
| `List` | source, item-template | lists |
| `Table` | columns, rows | tables |
| `Tabs` | items | tabbed views |
| `Modal` | open, title | dialogs |
| `Badge` | variant | status pills |
| `Icon` | name | iconography (token-colored) |

~12 primitives cover the declarative vocabulary. New attachment UIs compose these;
they almost never need new components.

## 7. Initial theme sets to ship

**Color (~15, curated from official specs):** Dracula, Gruvbox (dark), Gruvbox
(light), Nord, Catppuccin Mocha, Catppuccin Latte, Solarized Dark, Solarized Light,
Tokyo Night, One Dark, Monokai, Rosé Pine, Everforest, Kanagawa, Ayu.

**Concept (~10):** Flat (baseline, zero blur/shadow), Soft (subtle shadow + rounded),
Glassmorphism, Frosted (heavier blur, lighter alpha), Neobrutalism, Claymorphism,
Skeuomorph (inset/emboss), Outline (border-led, no fill), Material (elevation
shadows), Terminal (monospace, sharp, minimal).

## 8. Why this is maximally modular

- **Add a color theme:** one data file → appears in picker, works on every
  component and every concept. Zero code.
- **Add a concept theme:** one data file → same.
- **Add a component:** must read only tokens → instantly themeable by all themes.
- **Backend adds an attachment:** ships skeleton/wiring → rendered with existing
  themed components → no theme or frontend work.

The token contract (§3) is the single narrow waist everything passes through.
