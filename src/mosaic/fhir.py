"""FHIR clinical records parser for Apple Health exports."""
# ABOUTME: Parses FHIR R4 JSON files (DiagnosticReport, Observation) from
# ABOUTME: Apple Health exports into the clinical_labs DuckDB table.

import json
import sys
from pathlib import Path

import duckdb


def parse_clinical_records(
    conn: duckdb.DuckDBPyConnection,
    records_dir: Path,
) -> int:
    """Parse FHIR JSON files and insert lab results into clinical_labs.

    Handles DiagnosticReport (with embedded Observations) and standalone
    Observation resources. Skips non-lab and string-valued results.
    Uses INSERT OR IGNORE for deduplication on (draw_date, loinc_code).

    Returns the number of lab results inserted.
    """
    if not records_dir.exists():
        return 0

    labs: list[tuple[str, str, str, float, str, float | None, float | None, str]] = []
    seen: set[tuple[str, str, float]] = set()  # (loinc, date, value)

    for path in sorted(records_dir.iterdir()):
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        resource_type = data.get("resourceType", "")

        if resource_type == "DiagnosticReport":
            _extract_from_diagnostic_report(data, labs, seen)
        elif resource_type == "Observation":
            _extract_standalone_observation(data, labs, seen)

    if not labs:
        return 0

    # Batch insert with deduplication via INSERT OR IGNORE
    for lab in labs:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO clinical_labs
                (draw_date, test, loinc_code, value, unit,
                 ref_low, ref_high, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                list(lab),
            )
        except Exception:
            continue  # Skip malformed rows

    count_row = conn.sql("SELECT COUNT(*) FROM clinical_labs").fetchone()
    count: int = count_row[0] if count_row else 0
    print(
        f"  clinical records: {count} lab results from {records_dir}",
        file=sys.stderr,
    )
    return count


def _extract_observation_data(
    obs: dict[str, object],
) -> tuple[str, str, str, float, str, float | None, float | None] | None:
    """Extract lab data from a single FHIR Observation resource.

    Returns (date, test_name, loinc_code, value, unit, ref_low, ref_high)
    or None if the observation is not a numeric lab result.
    """
    if "valueQuantity" not in obs:
        return None

    # Get LOINC code and display name
    codings = obs.get("code", {})
    if isinstance(codings, dict):
        code_list = codings.get("coding", [])
    else:
        code_list = []

    loinc_code = ""
    display = ""
    for coding in code_list:
        system = str(coding.get("system", ""))
        if "loinc" in system.lower():
            loinc_code = str(coding.get("code", ""))
            display = str(coding.get("display", ""))
            break

    if not loinc_code:
        return None

    # Extract value
    vq = obs["valueQuantity"]
    if not isinstance(vq, dict) or "value" not in vq:
        return None
    value = float(vq["value"])
    unit = str(vq.get("unit", ""))

    # Extract date
    dt = str(obs.get("effectiveDateTime", ""))
    if not dt:
        return None
    draw_date = dt[:10]

    # Extract reference range
    ref_low: float | None = None
    ref_high: float | None = None
    ref_ranges = obs.get("referenceRange", [])
    if isinstance(ref_ranges, list) and ref_ranges:
        ref = ref_ranges[0]
        if isinstance(ref, dict):
            low = ref.get("low", {})
            high = ref.get("high", {})
            if isinstance(low, dict) and "value" in low:
                ref_low = float(low["value"])
            if isinstance(high, dict) and "value" in high:
                ref_high = float(high["value"])

    # Use code.text as fallback for display name
    if not display:
        display = str(codings.get("text", loinc_code))

    return (draw_date, display, loinc_code, value, unit, ref_low, ref_high)


def _extract_from_diagnostic_report(
    data: dict[str, object],
    labs: list[tuple[str, str, str, float, str, float | None, float | None, str]],
    seen: set[tuple[str, str, float]],
) -> None:
    """Extract lab results from a DiagnosticReport's contained Observations."""
    contained = data.get("contained", [])
    if not isinstance(contained, list):
        return

    for obs in contained:
        if not isinstance(obs, dict):
            continue
        if obs.get("resourceType") != "Observation":
            continue
        result = _extract_observation_data(obs)
        if result is None:
            continue
        draw_date, display, loinc, value, unit, ref_low, ref_high = result
        key = (loinc, draw_date, value)
        if key in seen:
            continue
        seen.add(key)
        labs.append(
            (draw_date, display, loinc, value, unit, ref_low, ref_high, "")
        )


def _extract_standalone_observation(
    data: dict[str, object],
    labs: list[tuple[str, str, str, float, str, float | None, float | None, str]],
    seen: set[tuple[str, str, float]],
) -> None:
    """Extract a lab result from a standalone Observation resource."""
    # Check category is laboratory
    categories = data.get("category", [])
    if isinstance(categories, dict):
        categories = [categories]
    if not isinstance(categories, list):
        return

    is_lab = False
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        for coding in cat.get("coding", []):
            if isinstance(coding, dict) and coding.get("code") == "laboratory":
                is_lab = True
                break
        if is_lab:
            break

    if not is_lab:
        return

    result = _extract_observation_data(data)
    if result is None:
        return
    draw_date, display, loinc, value, unit, ref_low, ref_high = result
    key = (loinc, draw_date, value)
    if key in seen:
        return
    seen.add(key)
    labs.append(
        (draw_date, display, loinc, value, unit, ref_low, ref_high, "")
    )
