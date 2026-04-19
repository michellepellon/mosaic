# Command Center UI Redesign

**Date:** 2026-04-19
**Status:** Approved

## Vibe: Graphite & Signal

Light dial base, almost monochrome. Color only when something needs attention.

**Palette:**
- Background: #f7f8fa (dial)
- Card: #ffffff
- Text: #1a1a2e (index)
- Borders: #e2e4e9
- Default/Good: #334155 (no color — good is the default state)
- Warning: #d97706 (amber)
- Redline: #ef4444 (red)
- Muted: #9ca3af

**Typography:**
- Display: Barlow Condensed (headers, score, section labels)
- Body: DM Sans (descriptions, prescriptions)
- Data: JetBrains Mono (numbers, SQL, metrics)

**Layout:** Dense, sharp edges, 1px borders, no rounded corners.

## Structure

1. **Header bar** — "MOSAIC" + date + data source
2. **Brief banner** — readiness score, prescription, factor scores, alerts
3. **Domain grid** (4 columns) — Recovery, Training, Fitness, Bloodwork
4. **Expanded card** (one at a time) — full charts + stats + SQL
5. **Console** (Cmd+K or bottom bar) — SQL query workspace

## Domain Cards (collapsed)

**Recovery:** Sleep hours (primary), HRV trend arrow + value, RHR value, SpO2 value, sparkline
**Training:** Weekly minutes (primary), session log (Mon: Run 45m Z2...), mini bar chart
**Fitness:** VO2 Max (primary), body fat %, gait speed, sparkline
**Bloodwork:** Last draw date (primary), draw count, panel status dots, flagged test

## Domain Cards (expanded)

Each expanded card shows:
- Full-width chart(s) with the domain's related metrics together
- Stats sidebar with current values, baselines, targets
- Flags/alerts specific to this domain
- Editable SQL query that generated the view

Only one card expanded at a time.

## Today / This Week toggle

Brief adapts: daily = readiness + prescription. Weekly = volume + recovery trend.
Domain cards adapt: daily = last night's data. Weekly = weekly aggregates.
