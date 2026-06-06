# DESIGN.md — Tearsheet (UI source of truth)

> Read this in full before any UI work. The aesthetic is a **deliberate point of view executed
> with precision**, not decoration. Commit fully.

## Aesthetic direction
**"Premium research terminal."** Warm charcoal + **cream** + a single **gold** accent. Refined,
data-dense, confident — like a modern fintech product (think Moonvest-style: dark surfaces with a
cream highlight card and gold accents), not a sterile dashboard and not a sharp Bloomberg clone.
Softly rounded cards, generous-but-tight spacing, tabular numerals everywhere. **Two themes** —
dark (default) and a **cream light mode (never plain white)** — switchable via a toggle.

## Hard rules (FORBIDDEN — the AI-slop tells)
- ❌ No plain white backgrounds. Light mode is **cream** (`#F3EEE2`), never `#FFFFFF`.
- ❌ No purple/violet gradients. No pastel "friendly fintech" rainbow.
- ❌ No Inter, Roboto, Arial, system-ui, or Space Grotesk as the primary face.
- ❌ No drop-shadow "floating card" soup. Shadows are subtle and single-layer.
- ❌ No evenly-distributed multi-colour palette. One dominant base + the gold accent; green/red
  for financial deltas only.
- ❌ No emoji as UI chrome.

## Colour tokens (CSS variables — single source of truth, see app/globals.css)
**Dark (default):** bg `#0D0F0E` · panel `#16191A` · cream-highlight `#F1E9D8` · border `#262A2B` ·
text `#ECEAE3` · muted `#97958C` · up `#45C26A` · down `#F0616D` · **accent (gold) `#E7B43C`**.

**Light (cream):** bg `#F3EEE2` · panel `#FBF8F0` · border `#E4DCC9` · text `#1C1812` ·
muted `#6E695B` · up `#2E9E54` · down `#D24B4B` · **accent (gold) `#B9841A`**.

One dominant base + one sharp gold accent beats a spread-out palette. Green-up / red-down is the
financial convention — deltas only, never decoration. The cream "feature" surface is used for the
one highlighted callout per module (the integrated-read / pre-mortem), echoing the reference style.

## Typography
- **Display / headings:** Mona Sans (industrial grotesque) — characterful, professional.
- **Body / UI:** Geist — clean, *not* Inter.
- **All numbers, tickers, prices, timestamps:** JetBrains Mono with `font-variant-numeric:
  tabular-nums`. This is the strongest "serious tool, not generated" signal — never drop it.

## Shape & motion
- **Radius:** cards `14px`, controls `9px`, pills fully rounded. Soft, not sharp; not bubbly.
- **Borders:** 1px hairline in the theme's border colour.
- **Elevation:** at most a single subtle shadow (stronger in light, near-zero in dark).
- **Motion:** exactly ONE restrained staggered reveal on load (~45ms apart). Theme switches
  cross-fade colours (0.25s). Nothing else moves. Crisp = credible.

## Layout
- **Left rail:** brand · **Theme toggle (Dark/Cream)** · **Data toggle (Live/Offline)** + data
  badge · ticker search · recent lookups · backend status.
- **Main area:** stacked rounded modules — Overview (+sparkline) · Interpretation · Why-did-it-move
  · Analysis · DCF · Valuation · Behaviour & Events · Financials · News.
- Right-align all numeric columns; tabular numerals so digits line up.
- **Footer:** monospace, muted — provenance + "not financial advice".

## Definition of done (UI)
- Passes the FORBIDDEN list. Light mode is cream, not white.
- Numerics are mono + tabular + right-aligned everywhere.
- Both themes look intentional; the toggle persists across reloads with no flash.
- One staggered load reveal; gold accent used sparingly; green/red for deltas only.
