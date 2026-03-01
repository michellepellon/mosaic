# Interactive Drill-Down Sidebar Design

**Date:** 2026-02-28
**Status:** Approved

## Problem

The Mosaic dashboard provides a dense, read-only overview of health metrics. Users want to drill into specific sections to see sub-metrics, expanded charts, and contextual detail without leaving the main view.

## Decision

Add a slide-over sidebar panel triggered by clicking section headings. The sidebar renders detailed sub-metric charts for the selected section using existing `rawData`.

Alternatives considered:
- **Inline accordion** — rejected due to layout shift disrupting the Tufte reading flow
- **Modal detail view** — rejected as too heavy for a personal dashboard; loses context

## Layout

- Fixed-position `<aside>` on the right edge, `380px` wide
- Slides in via CSS `transform: translateX` with `0.3s ease` transition
- Background `#fffff8`, left border `1px solid #ddd` — matches existing palette
- Close via `×` button or `Escape` key
- Section headings (`<h2>`) become clickable with `cursor: pointer` and a hover `›` indicator
- Responsive: full-width bottom sheet below `720px`; hidden in print

## Sidebar Content

### Protocol Scorecard
- Expanded sparklines (200×40px) for each metric
- Current value, 7-day avg, 30-day avg per metric
- Target value with status dot

### Clinical Biomarkers
- Historical lab values as scatter plot
- Reference range shading (green = optimal, red = danger)
- Date-based x-axis showing each test

### Trends
- Full-width chart (~340×200px) for selected metric
- 7-day and 30-day rolling average overlays
- Min/max/mean statistics for current date range

### Gait & Mobility
- Walking speed distribution histogram
- Asymmetry trend with target zone
- Step count vs. walking speed correlation

### Cardiovascular Detail
- RHR vs HRV scatter plot (colored by recency)
- HR zone distribution as weekly stacked bars

### Sleep Architecture
- Sleep stage percentages over time (line per stage)
- Sleep timing consistency (bedtime/wake scatter)
- Deep sleep % trend with target overlay

## Implementation Architecture

### DOM
```html
<aside id="sidebar" class="sidebar">
  <div class="sidebar-header">
    <h2 id="sidebar-title"></h2>
    <button id="sidebar-close" aria-label="Close">&times;</button>
  </div>
  <div id="sidebar-content"></div>
</aside>
```

### CSS (~80 lines)
- `.sidebar` — fixed, right, full-height, off-screen
- `.sidebar.open` — slides in
- Section headings — pointer cursor, hover arrow

### JavaScript (~200-250 lines)
- `openSidebar(sectionId)` — dispatches to section builder
- `closeSidebar()` — removes `.open`
- Six `buildSidebar*()` functions, one per section
- Single delegated click handler on `<article>`
- `renderAll()` re-renders sidebar if open on range change
- `Escape` key handler for close

### What doesn't change
- All existing chart functions untouched
- No new backend views or data sources
- No new dependencies
- Single HTML file architecture preserved

## Constraints
- Zero new dependencies
- Single HTML file
- Tufte-inspired aesthetic throughout
- Sidebar charts reuse existing D3 patterns (range frames, sparse axes, muted colors)
