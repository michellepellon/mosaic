"""Export dashboard data to JSON for the browser fallback path."""
# ABOUTME: Exports all dashboard view data from DuckDB to a single JSON file
# ABOUTME: for the browser fallback path when DuckDB-WASM is not available.

import json
from pathlib import Path

import duckdb

from mosaic.schema import LONGEVITY_THRESHOLDS, compute_lab_status


def _query(conn: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, object]]:
    """Run a query and return a list of dicts with JSON-safe values."""
    result = conn.sql(sql)
    cols = [d[0] for d in result.description]
    rows: list[dict[str, object]] = []
    for row in result.fetchall():
        obj: dict[str, object] = {}
        for c, v in zip(cols, row, strict=True):
            if hasattr(v, "isoformat"):
                obj[c] = str(v)[:10]
            elif isinstance(v, float):
                obj[c] = round(v, 2)
            elif v is None:
                obj[c] = None
            else:
                obj[c] = v
        rows.append(obj)
    return rows


def _transform_labs(lab_rows: list[dict[str, object]]) -> dict[str, object]:
    """Transform raw lab rows into the grouped format the dashboard expects."""
    if not lab_rows:
        return {"date": "", "source": "", "groups": {}}
    date = str(lab_rows[0].get("draw_date", ""))
    groups: dict[str, list[dict[str, object]]] = {}
    for row in lab_rows:
        loinc = str(row.get("loinc_code") or "")
        # Look up panel from LONGEVITY_THRESHOLDS by LOINC, fall back to "Other"
        threshold = LONGEVITY_THRESHOLDS.get(loinc, {})
        group = threshold.get("panel", "Other")
        optimal = threshold.get("optimal", "")
        if group not in groups:
            groups[group] = []
        status = compute_lab_status(
            float(row["value"]),  # type: ignore[arg-type]
            optimal,
        )
        groups[group].append({
            "test": row["test"],
            "value": row["value"],
            "unit": row["unit"],
            "optimal": optimal,
            "status": status,
        })
    return {"date": date, "source": "", "groups": groups}


def export_json(conn: duckdb.DuckDBPyConnection, path: Path) -> None:
    """Export all dashboard view data to a JSON file for the browser fallback."""
    lab_rows = _query(
        conn,
        "SELECT draw_date, test, loinc_code, value, unit, ref_low, ref_high "
        "FROM dashboard_labs ORDER BY test",
    )

    data: dict[str, object] = {
        "scorecard": _query(
            conn,
            "SELECT date AS d, steps, sleep, deep, rem, hr, hrv, "
            "spo2_min, spo2_avg FROM dashboard_scorecard ORDER BY date",
        ),
        "steps": _query(
            conn,
            "SELECT date AS d, total_steps AS v, r7, r30 "
            "FROM dashboard_steps ORDER BY date",
        ),
        "sleep": _query(
            conn,
            "SELECT date AS d, total, deep, rem FROM dashboard_sleep ORDER BY date",
        ),
        "rhr": _query(conn, "SELECT date AS d, v FROM dashboard_rhr ORDER BY date"),
        "hrv": _query(
            conn,
            "SELECT date AS d, v, r7, r30 FROM dashboard_hrv ORDER BY date",
        ),
        "spo2": _query(
            conn, "SELECT date AS d, min, avg FROM dashboard_spo2 ORDER BY date"
        ),
        "vo2": _query(conn, "SELECT date AS d, v FROM dashboard_vo2 ORDER BY date"),
        "bodyfat": _query(
            conn, "SELECT date AS d, v FROM dashboard_bodyfat ORDER BY date"
        ),
        "weight": _query(
            conn, "SELECT date AS d, v FROM dashboard_weight ORDER BY date"
        ),
        "exercise": _query(
            conn, "SELECT date AS d, v FROM dashboard_exercise ORDER BY date"
        ),
        "hrzones": _query(
            conn, "SELECT date AS d, z2, z4, total FROM dashboard_hrzones ORDER BY date"
        ),
        "walking_speed": _query(
            conn,
            "SELECT date AS d, v FROM dashboard_walking_speed ORDER BY date",
        ),
        "walking_asymmetry": _query(
            conn,
            "SELECT date AS d, v FROM dashboard_walking_asymmetry ORDER BY date",
        ),
        "respiratory_rate": _query(
            conn,
            "SELECT date AS d, v FROM dashboard_respiratory_rate ORDER BY date",
        ),
        "labs": _transform_labs(lab_rows),
        "lab_trends": _query(
            conn,
            "SELECT test, loinc_code, draw_date AS d, value, unit "
            "FROM dashboard_lab_trends",
        ),
        "longevity_thresholds": {
            loinc: {"panel": t["panel"], "display": t["display"], "optimal": t["optimal"]}
            for loinc, t in LONGEVITY_THRESHOLDS.items()
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str))
