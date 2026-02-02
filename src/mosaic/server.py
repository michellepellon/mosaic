"""MCP server exposing Mosaic health data to AI agents."""

import json
import os

import duckdb
from fastmcp import FastMCP

mcp = FastMCP(
    name="Mosaic Health",
    instructions=(
        "You are a longevity-focused health advisor with access to the user's Apple Health "
        "data and clinical lab results stored in a DuckDB database. Use the available tools "
        "to answer questions about their health metrics, trends, and biomarkers. "
        "When discussing lab results, use longevity-optimized thresholds (not standard "
        "reference ranges). Be specific with numbers and dates."
    ),
)

DB_PATH = os.environ.get("MOSAIC_DB", "data/health.duckdb")


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


def _query(sql: str, params: list[str] | None = None) -> list[dict[str, object]]:
    conn = _connect()
    try:
        result = conn.sql(sql, params=params) if params else conn.sql(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]
    finally:
        conn.close()


# ── Domain Tools ─────────────────────────────────────────────────


@mcp.tool
def get_health_summary(days: int = 30) -> dict[str, object]:
    """Get a protocol scorecard summarizing key health metrics over the last N days.

    Returns 30-day averages for: daily steps, sleep (total/deep/REM hours),
    resting heart rate, HRV, SpO2 min, VO2 Max (latest), body fat (latest),
    and weekly exercise minutes. Each metric includes a longevity target.
    """
    rows = _query(
        """
        SELECT * FROM dashboard_scorecard
        WHERE date >= CURRENT_DATE - CAST(? AS INTEGER)
        ORDER BY date
        """,
        [str(days)],
    )
    if not rows:
        return {"error": "No data found for the requested period"}

    def avg(key: str) -> float | None:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None  # type: ignore[arg-type]

    def latest(view: str, col: str) -> float | None:
        result = _query(f"SELECT {col} FROM {view} ORDER BY date DESC LIMIT 1")
        return result[0][col] if result else None  # type: ignore[return-value]

    exercise = _query(
        """
        SELECT AVG(v) AS avg_v FROM (
            SELECT v FROM dashboard_exercise ORDER BY date DESC LIMIT 4
        )
        """
    )
    ex_val = exercise[0]["avg_v"] if exercise else None
    ex_avg: float | None = round(float(ex_val), 0) if ex_val is not None else None  # type: ignore[arg-type]

    return {
        "period_days": days,
        "data_points": len(rows),
        "metrics": {
            "daily_steps": {"value": avg("steps"), "target": 10000},
            "sleep_hours": {"value": avg("sleep"), "target": 7.5},
            "deep_sleep_hours": {"value": avg("deep"), "target": 1.5},
            "rem_sleep_hours": {"value": avg("rem"), "target": 1.5},
            "resting_hr_bpm": {"value": avg("hr"), "target": 65, "lower_is_better": True},
            "hrv_ms": {"value": avg("hrv"), "target": 50},
            "spo2_min_pct": {"value": avg("spo2_min"), "target": 90},
            "vo2_max": {"value": latest("dashboard_vo2", "v"), "target": 40},
            "body_fat_pct": {
                "value": latest("dashboard_bodyfat", "v"),
                "target": 25,
                "lower_is_better": True,
            },
            "exercise_min_per_week": {"value": ex_avg, "target": 150},
        },
    }


@mcp.tool
def get_sleep_analysis(days: int = 30) -> dict[str, object]:
    """Analyze sleep patterns over the last N days.

    Returns nightly sleep data with total hours, deep sleep, REM sleep,
    and light sleep breakdown. Includes averages and the target of 7.5 hours.
    """
    rows = _query(
        """
        SELECT date, total, deep, rem,
               total - deep - rem AS light
        FROM dashboard_sleep
        WHERE date >= CURRENT_DATE - CAST(? AS INTEGER)
          AND total > 0.5
        ORDER BY date
        """,
        [str(days)],
    )
    if not rows:
        return {"error": "No sleep data found for the requested period"}

    totals = [r["total"] for r in rows]
    return {
        "period_days": days,
        "nights_recorded": len(rows),
        "averages": {
            "total_hours": round(sum(totals) / len(totals), 2),  # type: ignore[arg-type]
            "deep_hours": round(
                sum(r["deep"] for r in rows) / len(rows), 2  # type: ignore[arg-type]
            ),
            "rem_hours": round(
                sum(r["rem"] for r in rows) / len(rows), 2  # type: ignore[arg-type]
            ),
        },
        "target_hours": 7.5,
        "nightly_data": rows,
    }


@mcp.tool
def get_lab_results() -> dict[str, object]:
    """Get the most recent clinical lab results with longevity-optimized assessments.

    Returns lab values grouped by panel (Metabolic, Lipid, Hematology, Thyroid)
    with each test's value, unit, longevity-optimal range, and status
    (green = optimal, amber = acceptable, red = needs attention).
    """
    rows = _query("SELECT * FROM dashboard_labs ORDER BY test")
    if not rows:
        return {"error": "No lab data found. Import labs with: mosaic --labs labs.csv"}

    group_map: dict[str, str] = {
        "Glucose": "Metabolic Panel",
        "ALT": "Metabolic Panel",
        "AST": "Metabolic Panel",
        "Albumin": "Metabolic Panel",
        "Alkaline phosphatase": "Metabolic Panel",
        "BUN": "Metabolic Panel",
        "Creatinine": "Metabolic Panel",
        "Total bilirubin": "Metabolic Panel",
        "Potassium": "Metabolic Panel",
        "Sodium": "Metabolic Panel",
        "eGFR creat (CKD-EPI 2021)": "Metabolic Panel",
        "Cholesterol, total": "Lipid Panel",
        "HDL cholesterol": "Lipid Panel",
        "LDL cholesterol calculated": "Lipid Panel",
        "Non-HDL cholesterol": "Lipid Panel",
        "Triglycerides": "Lipid Panel",
        "Cholesterol/HDL ratio": "Lipid Panel",
        "WBC": "Hematology",
        "HGB": "Hematology",
        "HCT": "Hematology",
        "Platelet count": "Hematology",
        "Hemoglobin A1C": "Hematology",
        "TSH": "Thyroid",
    }

    groups: dict[str, list[dict[str, object]]] = {}
    date = None
    for row in rows:
        if date is None:
            date = row["date"]
        group = group_map.get(str(row["test"]), "Other")
        if group not in groups:
            groups[group] = []
        status = _compute_lab_status(row["value"], row.get("optimal"))  # type: ignore[arg-type]
        groups[group].append(
            {
                "test": row["test"],
                "value": row["value"],
                "unit": row["unit"],
                "optimal_range": row["optimal"],
                "longevity_target": row["longevity_target"],
                "status": status,
            }
        )

    return {"date": str(date), "panels": groups}


@mcp.tool
def get_cardio_trends(days: int = 90) -> dict[str, object]:
    """Get cardiovascular health trends over the last N days.

    Returns VO2 Max readings, resting heart rate trend, and HRV trend
    with rolling averages. Includes longevity targets.
    """
    vo2 = _query(
        "SELECT date AS d, v FROM dashboard_vo2 WHERE date >= CURRENT_DATE - CAST(? AS INTEGER)",
        [str(days)],
    )
    rhr = _query(
        "SELECT date AS d, v FROM dashboard_rhr WHERE date >= CURRENT_DATE - CAST(? AS INTEGER)",
        [str(days)],
    )
    hrv = _query(
        """SELECT date AS d, v, r7, r30 FROM dashboard_hrv
        WHERE date >= CURRENT_DATE - CAST(? AS INTEGER)""",
        [str(days)],
    )
    return {
        "period_days": days,
        "vo2_max": {"readings": vo2, "target": 40, "year1_target": 35},
        "resting_hr": {"daily": rhr, "target_bpm": 65, "lower_is_better": True},
        "hrv": {"daily": hrv, "target_ms": 50},
    }


@mcp.tool
def get_body_composition(days: int = 90) -> dict[str, object]:
    """Get body composition trends over the last N days.

    Returns body fat percentage and weight readings over time.
    """
    bodyfat = _query(
        """SELECT date AS d, v FROM dashboard_bodyfat
        WHERE date >= CURRENT_DATE - CAST(? AS INTEGER)""",
        [str(days)],
    )
    weight = _query(
        "SELECT date AS d, v FROM dashboard_weight WHERE date >= CURRENT_DATE - CAST(? AS INTEGER)",
        [str(days)],
    )
    return {
        "period_days": days,
        "body_fat_pct": {
            "readings": bodyfat,
            "target": 25,
            "lower_is_better": True,
        },
        "weight_lbs": {"readings": weight},
    }


# ── Raw SQL Escape Hatch ────────────────────────────────────────


@mcp.tool
def query_health_db(sql: str) -> list[dict[str, object]]:
    """Run a read-only SQL query against the full Mosaic health DuckDB.

    Use the health://schema resource to discover available tables and views.
    The database is opened read-only so only SELECT queries will work.

    Example: "SELECT date, total, deep, rem FROM dashboard_sleep ORDER BY date DESC LIMIT 7"
    """
    return _query(sql)


# ── Schema Resource ──────────────────────────────────────────────


@mcp.resource("health://schema")
def get_schema() -> str:
    """Database schema: all tables and views with their columns and types."""
    conn = _connect()
    try:
        tables = conn.sql(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
            """
        ).fetchall()
    finally:
        conn.close()

    schema: dict[str, list[dict[str, str]]] = {}
    for table_name, column_name, data_type in tables:
        if table_name not in schema:
            schema[table_name] = []
        schema[table_name].append({"column": column_name, "type": data_type})

    return json.dumps(schema, indent=2, default=str)


# ── Helpers ──────────────────────────────────────────────────────


def _compute_lab_status(value: float, optimal: object) -> str:
    opt = str(optimal) if optimal else ""
    if not opt or opt == "--" or opt == "None":
        return "green"
    if opt.startswith("<"):
        t = float(opt[1:])
        return "green" if value <= t else ("amber" if value <= t * 1.2 else "red")
    if opt.startswith(">"):
        t = float(opt[1:])
        return "green" if value >= t else ("amber" if value >= t * 0.8 else "red")
    parts = opt.split("-")
    if len(parts) == 2:
        try:
            lo, hi = float(parts[0]), float(parts[1])
        except ValueError:
            return "green"
        if lo <= value <= hi:
            return "green"
        margin = (hi - lo) * 0.2
        return "amber" if (lo - margin <= value <= hi + margin) else "red"
    return "green"


if __name__ == "__main__":
    mcp.run()
