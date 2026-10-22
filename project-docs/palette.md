# Map palette

Rules (CLAUDE.md): colorblind-safe, fixed bins, never party red or blue, and interface colors only in the chrome. The values live in `app/web/src/scales.ts` and `app/web/src/map/style.ts`. A unit test fails if any data color falls in the red (hue < 12° or > 345°) or blue (205–240°) range.

| Use | Colors | Validation (validate_palette.js, light, white surface) |
|---|---|---|
| Shares, turnout, totals (sequential, 8 bins) | teal `#d3eee7` → `#0c4037` | one hue (3° spread), lightness monotone, adjacent ΔL ≥ 0.06. The light end is below 2:1 by design: a choropleth's "near zero" may fade toward the surface, and white outlines separate areas. |
| Margins and yes share (diverging, 7 bins) | purple `#542788 #8d7fbf #c9c1e0`, gray `#e6e5e1`, orange `#f7c58a #e08214 #a14d07` | each arm is a single hue, monotone, with visible steps. The neutral gray middle means "within 5 points" (or 45–55% yes). |
| Leader by area (categorical, at most 3 + other) | `#eb6834` orange, `#1baf7a` aqua, `#6250d6` violet, other `#b8b6ae` | all pairs pass: CVD ΔE 9.2, normal-vision ΔE 27.6. Aqua is below 3:1 against white, so it relies on the legend, the tooltip and the detail table for relief. |

Non-data states never look like data:
- White: contest not on the ballot, no ballots cast, or no data.
- Gray with dots: not in Columbus (council view only).
- Diagonal hatch rising left to right ("/") over the data color: fewer than 25 valid votes (property: 25 parcels; census: margin of error too large). It's the only diagonal pattern.
- Legend swatches are drawn from the same pixel tiles the map uses (`hatchImage`, `dotsImage` and `patternBackground` in `app/web/src/map/style.ts`), so the legend can't drift from the map.
- Opaque off-white mask: outside Franklin County.

Colors follow a candidate's contest-wide rank, never their party.
