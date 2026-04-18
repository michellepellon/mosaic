# Longevity Dashboard Improvements

**Date:** 2026-04-18
**Status:** Approved

## Problem

The Mosaic dashboard tracks the right longevity biomarkers but has three credibility and utility gaps:

1. **Fabricated HR zones** -- the cardiovascular section estimates Zone 2/Zone 4 time using fixed percentages of workout duration (40%/10%) rather than actual heart rate data. This makes the chart unusable for verifying training compliance.
2. **Single-snapshot labs** -- clinical biomarkers show only the most recent draw with no longitudinal tracking. Labs imported via manual CSV when the Apple Health export already contains structured FHIR clinical records from EPIC.
3. **Isolated metrics** -- nine trend charts are presented as independent silos with no cross-metric correlation, preventing users from seeing cause-effect relationships (e.g., poor sleep driving HRV suppression).

## Implementation Sequence

1. Real HR Zones (most impactful credibility fix)
2. FHIR Clinical Records Parser + Longitudinal Labs
3. Cross-Metric Correlation (Tier 1 Triad)

Each improvement is independently deployable.

---

## Improvement 1: Real HR Zones

### CLI

New optional flag: `--max-hr <int>`. If omitted, max HR is estimated from date of birth in the export XML using Tanaka's formula: `208 - 0.7 * age`.

### Zone Model

Zones are computed as percentage of max HR. All five zones are stored; the dashboard displays a longevity-focused breakdown (Z2 / Z4+ / Other).

| Zone | Range     | Label         |
|------|-----------|---------------|
| Z1   | < 60%     | Recovery      |
| Z2   | 60-70%    | Aerobic Base  |
| Z3   | 70-80%    | Tempo         |
| Z4   | 80-90%    | Threshold     |
| Z5   | 90%+      | VO2 Max       |

### Parser Changes

- Extract date of birth from the `<Me>` element during XML parsing.
- After all records are ingested (but before views are created), run a post-processing pass:
  - For each workout in the `workouts` table, query `heart_rate_samples` where `start_date` falls within the workout's start/end time window.
  - Classify each HR sample into a zone using max HR (user-provided or estimated).
  - Compute time-in-zone per sample using `end_date - start_date`.
  - Insert one row per zone per workout into `workout_hr_zones`.
- If no HR samples overlap a workout (e.g., gym equipment workout without watch), that workout contributes zero zone data -- no fabrication.

### New Table

```sql
CREATE TABLE IF NOT EXISTS workout_hr_zones (
    workout_start   TIMESTAMPTZ NOT NULL,
    workout_type    VARCHAR NOT NULL,
    zone            INTEGER NOT NULL,    -- 1-5
    seconds         DOUBLE NOT NULL,
    source_name     VARCHAR NOT NULL
)
```

### Replaced View

The existing `dashboard_hrzones` view is replaced with:

```sql
CREATE OR REPLACE VIEW dashboard_hrzones AS
SELECT DATE_TRUNC('week', workout_start::TIMESTAMP)::DATE AS date,
    SUM(seconds) FILTER (WHERE zone = 2) / 60.0 AS z2,
    SUM(seconds) FILTER (WHERE zone >= 4) / 60.0 AS z4,
    SUM(seconds) / 60.0 AS total
FROM workout_hr_zones
GROUP BY 1 ORDER BY 1
```

### Dashboard Changes

The existing HR zone stacked bar chart picks up real data automatically. The "Other" segment computation changes from pulling exercise view data to using `total - z2 - z4` from the view.

### What Stays the Same

The `workouts` table, all other views, the scorecard, and MCP server tools are unchanged.

---

## Improvement 2: FHIR Clinical Records Parser + Longitudinal Labs

### Zip Extraction

`resolve_xml_path()` expands to also extract `clinical-records/` from the zip when present. Returns both the XML path and the clinical records directory path.

### New Module: `fhir.py`

A dedicated module for FHIR JSON parsing. Responsibilities:

- Scan a directory of FHIR JSON files.
- Extract lab results from `DiagnosticReport` resources (which embed `Observation` resources in `contained`) and standalone `Observation` resources with `category=laboratory`.
- Deduplicate: the same result often appears as both a standalone Observation and embedded in a DiagnosticReport. Deduplicate by LOINC code + effectiveDateTime + value.
- Use `display` field from FHIR `code.coding` for human-readable test names (not hardcoded mappings).
- Use `referenceRange.low/high` for standard reference ranges.
- Use `effectiveDateTime` as the draw date.

### Expanded Table: `clinical_labs`

```sql
CREATE TABLE IF NOT EXISTS clinical_labs (
    draw_date     DATE NOT NULL,
    test          VARCHAR NOT NULL,
    loinc_code    VARCHAR,
    value         DOUBLE NOT NULL,
    unit          VARCHAR,
    ref_low       DOUBLE,
    ref_high      DOUBLE,
    source        VARCHAR,
    UNIQUE(draw_date, loinc_code)
)
```

Changes from current schema:
- `date` renamed to `draw_date`.
- `loinc_code` added for standardized identification across providers.
- `source` added (e.g., "Labcorp", "EPIC").
- `longevity_target` and `optimal` columns removed from the table. These are domain knowledge, not raw data, and move to a display-time lookup.
- `UNIQUE(draw_date, loinc_code)` prevents duplicates on re-import.

### Longevity Thresholds Lookup

A new dict in `schema.py` -- `LONGEVITY_THRESHOLDS` -- keyed by LOINC code (with test name fallback). Each entry contains:

- `panel`: panel group name (e.g., "Metabolic Panel", "Lipid Panel")
- `optimal`: optimal range string using the existing format (`"<90"`, `">40"`, `"72-85"`)
- `display`: canonical display name (overrides FHIR display when present)

This is the single source of truth, replacing the duplicated `_LAB_GROUPS` and `_compute_lab_status` in `export.py` and `server.py`. The `_compute_lab_status` logic moves to a shared function in `schema.py`.

### New Views

```sql
CREATE OR REPLACE VIEW dashboard_labs AS
SELECT draw_date, test, loinc_code, value, unit, ref_low, ref_high, source
FROM clinical_labs ORDER BY draw_date DESC, test

CREATE OR REPLACE VIEW dashboard_lab_trends AS
SELECT test, loinc_code, draw_date, value, unit, ref_low, ref_high
FROM clinical_labs
ORDER BY test, draw_date
```

### CLI Changes

- FHIR parsing happens automatically when the zip contains `clinical-records/`. No flag needed.
- `--labs` CSV flag still works as a fallback. Column names change to match the new schema (drop `longevity_target`/`optimal`, add optional `loinc_code`/`source`).
- If both FHIR records and `--labs` CSV are provided, both are imported. The UNIQUE constraint handles deduplication.

### Dashboard Changes

- Biomarkers section shows the most recent draw (same as today) with a small "N draws" indicator showing how many historical draws exist.
- The longevity threshold lookup (`LONGEVITY_THRESHOLDS`) is exported to JSON alongside the lab data so the dashboard can compute status colors client-side.
- Sidebar drill-down for biomarkers gets a longitudinal scatter plot per test: each dot is a draw date, with reference range shading and longevity optimal range overlaid.
- Trend arrows on each test showing direction vs the prior draw.

### Breaking Change

The `--labs` CSV column format changes (`longevity_target`/`optimal` removed, `loinc_code`/`source` added). The CSV path was never a public API and becomes secondary to the FHIR path.

### Test Updates

Existing tests in `test_cli.py` and `test_export.py` that reference the old `clinical_labs` schema (columns `longevity_target`, `optimal`) must be updated to match the new schema. Test CSV fixtures change accordingly.

---

## Improvement 3: Cross-Metric Correlation (Tier 1 Triad)

### New Dashboard Section: "Cross-Metric Correlations"

Placed between Trends and Cardiovascular Detail. Brief intro text: "Paired metrics that reveal cause-effect relationships. These three pairings cover the most common longevity interventions: optimize sleep, calibrate training, screen for apnea."

### Chart 1: HRV vs Sleep Quality

- Left y-axis: HRV (ms), 7-day rolling average line.
- Right y-axis: Deep + REM hours, stacked bars (same colors as sleep architecture section).
- Shared x-axis: date.
- Annotation: highlight periods where HRV drops >15% week-over-week by marking the corresponding sleep bars.
- Sidenote: "Autonomic recovery is gated by sleep architecture. Chronically low HRV with adequate sleep suggests overtraining; low HRV with poor sleep suggests fixing sleep first."

### Chart 2: RHR Trend vs Training Load

- Left y-axis: Resting HR (bpm), 7-day rolling average line.
- Right y-axis: Weekly exercise minutes, bars.
- Shared x-axis: date (weekly granularity).
- Annotation: highlight periods where RHR rises while training volume is stable or increasing.
- Sidenote: "Rising resting HR during stable training volume is the earliest signal of overtraining or illness. Well-adapted training shows declining RHR with increasing load."

### Chart 3: SpO2 Nadir vs Deep Sleep

- Left y-axis: Nightly SpO2 minimum (%), scatter with connecting line.
- Right y-axis: Deep sleep hours, bars.
- Shared x-axis: date.
- Annotation: mark nights where SpO2 < 90% with red dots; highlight whether deep sleep was also suppressed.
- Sidenote: "Nocturnal desaturation disrupts deep sleep via microarousals. If deep sleep is chronically low and SpO2 dips below 90%, a sleep study should be considered."
- Danger threshold line at 88% SpO2.

### Visual Style

- Full-width charts (~920px), matching sleep architecture section.
- Tufte aesthetic: sparse axes, muted fills, ET Book font.
- Sidenote-style clinical context in the right margin using the existing `<aside>` pattern.
- Consistent color language: HRV/HR lines in dark gray, sleep bars in the deep/REM/light palette, SpO2 in the existing min/avg colors.

### Data Source

No new tables or views. Charts join existing dashboard views client-side by date, following the same pattern as `dashboard_scorecard`.

### Sidebar Drill-Down

Clicking the "Cross-Metric Correlations" heading opens a sidebar with Tier 2 pairs:
- HRV vs RHR scatter plot (reuse from cardiovascular sidebar).
- Steps vs Sleep Duration dual-axis chart.

---

## Scope Exclusions

The following items surfaced during critique but are explicitly out of scope for this work:

- Age/sex-stratified targets for the protocol scorecard
- Blood pressure parsing (skipped record type in parser)
- Sleep efficiency and timing consistency charts
- Stride length visualization
- Intervention guidance in the biomarkers section
- Seasonal markers or user-annotated events on timelines
- Confidence intervals on Apple Watch-derived estimates (VO2 Max, sleep stages)
