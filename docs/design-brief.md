# Design brief: direction C, "Timetable"

Chosen 2026-11-27. The mock-ups it came from: `docs/design/c-timetable-*.png`.

## Idea

A plain, dense tool that reads like a printed timetable or a departures board: big type for the thing you choose, small type for the details, heavy black rules between sections. It should look like it was made for this job, not from a template.

## Type

- **Libre Franklin** only: 400 for body text, 600 for labels and course codes, 800 for big names (campus list, the chosen major).
- **Tabular figures** (`font-variant-numeric: tabular-nums`) wherever numbers line up: units, totals, GPA, counts.
- Sizes: body 16px; course codes 16px/600; section names 22px/800; campus names 34px/800 (26px on phones).

## Color

| Token | Hex | Use |
|---|---|---|
| `--ink` | `#16181d` | body text, heavy rules |
| `--muted` | `#5b616b` | titles under codes, secondary text |
| `--hair` | `#d8dadf` | thin rules between rows |
| `--paper` | `#ffffff` | background |
| `--hi` | `#f2c230` | "you are here": the current term, the chosen campus number. Never for text on white. |
| `--ok` | `#1f7a3a` | "Ready", taken, requirement met |

The map keeps its working colors: red for "what it needs", blue for "what it unlocks". Nothing else gets color.

## Layout rules

- **Rules, not cards:** sections are separated by a 3px ink rule on top; rows by a 1px hair rule. No shadows, no rounded cards.
- **Header:** the name as a plain wordmark, then the campus name and a "change" link, then Credit / Help / About on the right. A 3px ink rule under it. No tagline.
- **Campus screen:** a numbered list, one campus per row, in UC's own order. Campuses that aren't ready are grey and can't be picked. Keys 1 to 9 pick a ready campus.
- **Plan:** term columns in a dense grid; the current term's header has the yellow background. Requirements as rows with a fraction ("4 / 7") and a thin bar.
- **Phones:** one column; the same rules and type, smaller campus names.

## Copy

- Sentence case everywhere. Buttons name the action.
- "Unofficial" is said once, in About.
- No middots in labels, no arrows on buttons, no ALL-CAPS labels.

## Motion

Only in answer to a click (the course panel opening). `prefers-reduced-motion` turns it off.

## Checks before shipping

- The silhouette test: with the text blurred, it should not look like a generic SaaS page.
- The checklist in `PLAN-all-uc.md`, "Design: not looking machine-made".
- Contrast: all text at least 4.5:1 (yellow is only a background behind ink).
