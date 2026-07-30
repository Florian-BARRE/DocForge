# DocForge — Brand charter

> "A document is melted down, cast into chunks, and stored as vectors you can strike again."
> The whole system dresses that one idea.

## Philosophy

- **Warm, not neutral.** The ground is warm paper, the text warm graphite — a workshop, not a
  spreadsheet. Cool greys are banned.
- **Orange means work.** Forge orange is never decoration. It marks the one thing being worked:
  a running job, the active stage, the primary action, the retrieved neighbourhood.
- **Dense, legible cockpit.** Tight rows and real data everywhere, but every value stays readable —
  nothing shrinks below 11px.
- **Serif-free, machine-honest.** Archivo is the whole UI voice; JetBrains Mono is reserved for
  anything the machine emits (ids, hashes, scores, timings, dimensions, versions).

## Color

### Grounds & ink
| Name | Hex | Use |
|---|---|---|
| Paper | `#f7f5f2` | app ground (light) |
| Sheet | `#efece7` | panels, table headers, hovers |
| White | `#ffffff` | cards |
| Ink | `#14161a` | primary text / dark ground |
| Press ink | `#1b1d22` | raised surface in dark mode |
| Steel | `#3d454f` | secondary text / meta |
| Muted | `#8a8378` | labels, timestamps (warm grey) |
| Muted (dark) | `#8b939d` | labels on ink |

### Forge ramp (the working ink) — OKLCH-even steps
`100 #fdf1e7 · 200 #fbdcc3 · 300 #f6bd8f · 400 #ef9455 · 500 #ef5b1e · 600 #c1440a · 700 #9c3406 · 800 #742706 · 900 #4a1c09`
- **500 `#ef5b1e`** — base fill (buttons, running, active).
- **600 `#c1440a`** — accent **text** on paper (500 fails body contrast), pressed state.
- On the **ink** theme the accent steps one lighter to **`#ef7a45`**.
- **Ember `#f4a63b`** — warn / stale tint only.

### Pipeline states — one ink per meaning, no green but "done"
| State | Light | Dark |
|---|---|---|
| Running | `#ef5b1e` | `#ef7a45` |
| Done | `#2f7d4f` | `#4bb67e` |
| Error | `#c8402c` | `#f06a52` |
| Pending / warning | `#8a8378` | `#8b939d` |
| Skipped | `#b0a99c` (dashed dot) | `#5a6068` (dashed dot) |
| Stale | `#f4a63b` | `#f4a63b` |

## Type

- **Archivo** — UI: 800 titles (`-0.035em`), 700 headings (`-0.02em`), 400–600 body/labels ~13.5px.
- **JetBrains Mono** — machine values only: ids, hashes, scores, timings, dims, versions,
  section labels (10px uppercase, `+0.16em`).

## Iconography

Cut from the logo: page → melt → cast → store → strike. Each stage glyph keeps one **hot cell**
(`#ef5b1e`) = the element being worked; everything else is `currentColor`. Never emoji.

## Do
- Take every color/font/size from the tokens; never hard-code.
- Use forge for the single active/primary thing; steel + muted for everything at rest.
- Keep the serif out — Archivo is the chrome.
- Truncate ids/slugs; let names lead.

## Don't
- No indigo, no cool slate, no second accent family.
- No green except the single "done" forest tone.
- No forge orange as background wallpaper or gradient wash.
- No text set in mono; no value shrunk below 11px.
