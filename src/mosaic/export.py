"""Export dashboard data to JSON for the browser fallback path."""

import json
from pathlib import Path

import duckdb

# Lab panel groupings — must match dashboard.html transformLabs()
_LAB_GROUPS: dict[str, str] = {
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


def _compute_lab_status(value: float, optimal: object) -> str:
    """Compute green/amber/red status for a lab result vs its optimal range."""
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
    date = str(lab_rows[0].get("date", ""))
    groups: dict[str, list[dict[str, object]]] = {}
    for row in lab_rows:
        test_name = str(row["test"])
        group = _LAB_GROUPS.get(test_name, "Other")
        if group not in groups:
            groups[group] = []
        status = _compute_lab_status(
            float(row["value"]),  # type: ignore[arg-type]
            row.get("optimal"),
        )
        groups[group].append({
            "test": row["test"],
            "value": row["value"],
            "unit": row["unit"],
            "optimal": row.get("optimal", ""),
            "status": status,
        })
    return {"date": date, "source": "", "groups": groups}


def export_json(conn: duckdb.DuckDBPyConnection, path: Path) -> None:
    """Export all dashboard view data to a JSON file for the browser fallback."""
    lab_rows = _query(
        conn,
        "SELECT date, test, value, unit, longevity_target, optimal "
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
            conn, "SELECT date AS d, z2, z4 FROM dashboard_hrzones ORDER BY date"
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
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str))
