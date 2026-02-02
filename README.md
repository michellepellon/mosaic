# Mosaic

Parse Apple Health exports into DuckDB and visualize longevity-focused biomarkers.

Mosaic takes the XML export from the Apple Health app, streams it into a DuckDB database with pre-aggregated views, and renders an interactive dashboard for tracking health metrics against longevity-optimized targets.

## Quick Start

```bash
# Install (requires Python 3.14+)
uv sync

# Parse your Apple Health export
uv run mosaic export.xml -o data/health.duckdb

# Or from a zip file
uv run mosaic apple_health_export.zip -o data/health.duckdb

# Import lab results (optional)
uv run mosaic export.xml -o data/health.duckdb --labs data/labs.csv
```

### Export from Apple Health

1. Open the **Health** app on your iPhone
2. Tap your profile picture (top right)
3. Scroll to **Export All Health Data**
4. Transfer the resulting zip to your computer

## Dashboard

The dashboard (`dashboard.html`) uses DuckDB-WASM to query `data/health.duckdb` directly in the browser. No export step needed.

1. Parse your data (see Quick Start above)
2. Serve locally: `python3 -m http.server 8080`
3. Open `http://localhost:8080/dashboard.html`

If no `.duckdb` file is found, the dashboard falls back to loading `data/embedded_data.json`. A sample dataset (`data/sample_data.json`) is included to preview the layout -- copy it to `data/embedded_data.json` to see the dashboard with synthetic data.

### Sections

- **Protocol Scorecard** -- 30-day averages for steps, sleep, HR, HRV, VO2 Max, body fat, exercise, and SpO2 with sparklines and bullet charts vs targets
- **Clinical Biomarkers** -- Lab results with longevity-optimized thresholds (not standard reference ranges)
- **Trends** -- Small multiples for 8 biomarkers over time with target and danger threshold lines
- **Cardiovascular Detail** -- VO2 Max trajectory with year-end projection; HR zone distribution
- **Sleep Architecture** -- Nightly stacked bars (deep/REM/light) plus SpO2 companion chart highlighting desaturation events

## DuckDB Views

Mosaic creates these pre-aggregated views on top of the raw records:

| View | Description |
|------|-------------|
| `daily_steps` | Daily step totals |
| `daily_heart_rate` | Daily resting HR (min of daily averages) |
| `daily_sleep` | Sleep duration and stage breakdown per night |
| `daily_energy` | Active + basal energy by day |
| `vo2_max_trend` | VO2 Max readings over time |
| `body_composition_trend` | Body fat %, lean mass, BMI |
| `sleep_sessions_summary` | Merged sleep session data |

Dashboard-specific views (used by DuckDB-WASM in the browser):

| View | Description |
|------|-------------|
| `dashboard_steps` | Daily steps with 7d and 30d rolling averages |
| `dashboard_sleep` | Nightly sleep in hours with deep/REM breakdown |
| `dashboard_rhr` | Daily resting heart rate |
| `dashboard_hrv` | Daily HRV with rolling averages |
| `dashboard_spo2` | Daily SpO2 min and average |
| `dashboard_vo2` | VO2 Max readings |
| `dashboard_bodyfat` | Body fat percentage over time |
| `dashboard_weight` | Weight in lbs over time |
| `dashboard_exercise` | Weekly exercise minutes |
| `dashboard_hrzones` | Weekly HR zone distribution (estimated) |
| `dashboard_scorecard` | Daily composite for protocol scorecard |
| `dashboard_labs` | Clinical lab results |

## Architecture

```
export.xml (50-200 MB)     labs.csv (optional)
    |                           |
    v  streaming iterparse      v  read_csv_auto
+-----------+
|  DuckDB   |  15 raw tables + 20 pre-aggregated views
+-----------+
    |
    v  DuckDB-WASM (in-browser)
+---------------+
| dashboard.html|  D3.js + Tufte CSS, no build step
+---------------+
```

- **Parser**: Streaming `xml.etree.ElementTree.iterparse` with PyArrow record batches flushed to DuckDB every 50,000 rows. Memory-efficient on 200MB+ exports.
- **Schema**: Type registry maps Apple Health `HKQuantityTypeIdentifier` strings to DuckDB tables. Views handle aggregation and rolling averages. Dashboard views pre-shape data for the browser.
- **Dashboard**: Single HTML file using D3.js v7, DuckDB-WASM, and ET Book. No build tools, no framework. Queries the `.duckdb` file directly via DuckDB-WASM (~3.2 MB, CDN-cached). Falls back to JSON if no database file is available.
- **Labs**: Clinical lab results imported via `--labs` flag from CSV. Supports longevity-optimized thresholds.

## Docker

```bash
# 1. Drop your Apple Health export into data/
cp ~/export.xml data/export.xml
cp ~/labs.csv data/labs.csv        # optional

# 2. Parse the export (one-shot, run once)
docker compose --profile parse run --rm parser

# 3. Start the dashboard and MCP server
docker compose up -d
```

- **Dashboard**: http://localhost:3000
- **MCP server**: http://localhost:8080/mcp

To connect an AI agent to the MCP server:

```json
{
  "mcpServers": {
    "mosaic": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

Re-parse after a new export: `docker compose --profile parse run --rm parser`

## MCP Server

The MCP server exposes your health data to AI agents. Available tools:

| Tool | Description |
|------|-------------|
| `get_health_summary` | Protocol scorecard: steps, sleep, HR, HRV, VO2, body fat, exercise, SpO2 |
| `get_sleep_analysis` | Nightly sleep breakdown with deep/REM/light trends |
| `get_lab_results` | Lab results with longevity-optimized status (green/amber/red) |
| `get_cardio_trends` | VO2 Max, resting HR, and HRV over time |
| `get_body_composition` | Body fat and weight trends |
| `query_health_db` | Raw read-only SQL against the full DuckDB |

Run locally without Docker:

```bash
MOSAIC_DB=data/health.duckdb uv run mosaic-server
```

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Type check
uv run pyright

# Lint
uv run ruff check
```

## License

MIT
