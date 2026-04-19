# Daily Action Brief

**Date:** 2026-04-19
**Status:** Approved

## Problem

The Mosaic dashboard shows what happened but doesn't tell you what to do. A performance center answers three questions the moment you walk in: How did I recover? What should I do today? What should I watch?

## Design

### New Section: Daily Action Brief

Replaces the Protocol Scorecard as the first thing you see. The scorecard moves below it.

#### Readiness Score (0-100)

Composite score from last night's data vs 30-day baseline:

| Factor | Weight | Source |
|---|---|---|
| HRV vs 30d baseline | 30% | `dashboard_hrv` |
| RHR vs 30d baseline | 20% | `dashboard_rhr` |
| Sleep total vs 7.5h target | 20% | `dashboard_sleep` |
| Deep + REM vs baseline | 15% | `dashboard_sleep` |
| SpO2 nadir vs 90% floor | 10% | `dashboard_spo2` |
| Prior day training load | 5% | `dashboard_exercise` |

Scoring per factor: at baseline = 75, 10%+ above = 100, 10%+ below = 50, 20%+ below = 25. Weighted average gives composite.

#### Training Prescription

| Score | Status | Color | Prescription |
|---|---|---|---|
| 85-100 | Peak | Green | High-intensity intervals, heavy strength, or long endurance |
| 70-84 | Ready | Yellow-green | Zone 2 aerobic base, moderate strength |
| 50-69 | Moderate | Amber | Light Zone 2, mobility work, yoga |
| 0-49 | Recover | Red | Walk only. Prioritize sleep tonight. |

#### Watch List

Automated flags shown only when triggered:

- HRV trending down 3+ consecutive days
- Deep sleep < 1hr for 3+ consecutive nights
- SpO2 dropped below 88% last night
- RHR rising while training volume stable (7d RHR up, 7d exercise flat/up)
- No Zone 2 training this week
- Training load spike (this week > 1.5x 4-week average)

#### Visual Treatment

- Full-width banner with large readiness number (72pt-equivalent)
- Status word below in small caps (PEAK / READY / MODERATE / RECOVER)
- Color-coded background tint (very subtle, Tufte-appropriate -- not garish)
- Training prescription as a single bold sentence
- Watch list as small alert items below, muted unless red
- Date and "last sync" timestamp

### MCP Tool: get_daily_brief

New MCP tool returning the same data programmatically:

```python
@mcp.tool
def get_daily_brief() -> dict[str, object]:
    """Get today's performance readiness score, training prescription,
    and watch list alerts."""
```

Returns: readiness score, status, prescription text, contributing factors with individual scores, and active alerts.

### Implementation

- New `buildDailyBrief(data)` function in dashboard.html
- Readiness computation in a shared function usable by both dashboard and MCP
- New Python module `src/mosaic/readiness.py` for the computation logic (shared between dashboard JSON export and MCP server)
- Dashboard scorecard section moves below the brief

## Scope Exclusions

- No subjective wellness input (manual journaling) -- future work
- No nutrition domain -- future work
- No mental performance domain -- future work
- No push notifications -- requires mobile app
