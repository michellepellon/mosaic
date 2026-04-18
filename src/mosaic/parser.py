"""Streaming XML parser for Apple Health exports."""

import re
import sys
from collections import defaultdict
from pathlib import Path
from xml.etree.ElementTree import Element, iterparse

import duckdb as _duckdb
import pyarrow as pa

from mosaic.schema import BODY_MEASUREMENT_TYPES, SLEEP_STAGES, TYPE_REGISTRY, WALKING_METRIC_TYPES

# Tuple types for each table shape
type QuantityRow = tuple[str, str | None, str, float, str, str, str | None]
type SleepRow = tuple[str, str | None, str, str, str, str | None]
type WorkoutRow = tuple[
    str, str, str | None, float | None, float | None, float | None, str, str, str | None
]
type ActivitySummaryRow = tuple[
    str, float | None, float | None, float | None, float | None, float | None, float | None
]
type BodyMeasurementRow = tuple[str, str | None, str, str, float, str, str, str | None]
type WalkingMetricRow = tuple[str, str | None, str, str, float, str, str, str | None]


def _opt_float(val: str | None) -> float | None:
    """Convert an optional string to float, returning None if absent."""
    return float(val) if val is not None else None


def _fix_tz(ts: str) -> str:
    """Normalize Apple Health timestamp for DuckDB TIMESTAMPTZ.

    Converts '2024-03-15 08:30:00 -0600' to '2024-03-15 08:30:00-06:00'.
    DuckDB requires no space before offset and colon between hours/minutes.
    """
    # Match ' -0600' or ' +0530' at end of string
    if len(ts) >= 6 and ts[-5] in ("+", "-") and ts[-4:].isdigit():
        offset = ts[-5:-2] + ":" + ts[-2:]
        base = ts[:-5]
        # Remove trailing space before offset if present
        if base.endswith(" "):
            base = base[:-1]
        return base + offset
    return ts


def _fix_tz_opt(ts: str | None) -> str | None:
    """Apply _fix_tz to an optional timestamp string."""
    return _fix_tz(ts) if ts is not None else None


def _normalize_workout_type(hk_type: str) -> str:
    """Convert HKWorkoutActivityTypeRunning -> running."""
    name = hk_type.removeprefix("HKWorkoutActivityType")
    # Insert underscore before uppercase letters and lowercase everything
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def extract_quantity_record(elem: Element) -> QuantityRow:
    """Extract a standard quantity record (steps, HR, energy, etc.)."""
    return (
        elem.attrib["sourceName"],
        elem.attrib.get("sourceVersion"),
        elem.attrib["unit"],
        float(elem.attrib["value"]),
        _fix_tz(elem.attrib["startDate"]),
        _fix_tz(elem.attrib["endDate"]),
        _fix_tz_opt(elem.attrib.get("creationDate")),
    )


def extract_sleep_record(elem: Element) -> SleepRow:
    """Extract a sleep analysis record with human-readable stage."""
    raw_value = elem.attrib["value"]
    stage = SLEEP_STAGES.get(raw_value, raw_value)
    return (
        elem.attrib["sourceName"],
        elem.attrib.get("sourceVersion"),
        stage,
        _fix_tz(elem.attrib["startDate"]),
        _fix_tz(elem.attrib["endDate"]),
        _fix_tz_opt(elem.attrib.get("creationDate")),
    )


def extract_workout(elem: Element) -> WorkoutRow:
    """Extract a workout element."""
    return (
        _normalize_workout_type(elem.attrib["workoutActivityType"]),
        elem.attrib["sourceName"],
        elem.attrib.get("sourceVersion"),
        _opt_float(elem.attrib.get("duration")),
        _opt_float(elem.attrib.get("totalDistance")),
        _opt_float(elem.attrib.get("totalEnergyBurned")),
        _fix_tz(elem.attrib["startDate"]),
        _fix_tz(elem.attrib["endDate"]),
        _fix_tz_opt(elem.attrib.get("creationDate")),
    )


def extract_activity_summary(elem: Element) -> ActivitySummaryRow:
    """Extract an ActivitySummary element."""
    return (
        elem.attrib["dateComponents"],
        _opt_float(elem.attrib.get("activeEnergyBurned")),
        _opt_float(elem.attrib.get("activeEnergyBurnedGoal")),
        _opt_float(elem.attrib.get("appleExerciseTime")),
        _opt_float(elem.attrib.get("appleExerciseTimeGoal")),
        _opt_float(elem.attrib.get("appleStandHours")),
        _opt_float(elem.attrib.get("appleStandHoursGoal")),
    )


def extract_body_measurement(elem: Element, hk_type: str) -> BodyMeasurementRow:
    """Extract a body measurement record with a measurement discriminator."""
    measurement = BODY_MEASUREMENT_TYPES[hk_type]
    return (
        elem.attrib["sourceName"],
        elem.attrib.get("sourceVersion"),
        measurement,
        elem.attrib["unit"],
        float(elem.attrib["value"]),
        _fix_tz(elem.attrib["startDate"]),
        _fix_tz(elem.attrib["endDate"]),
        _fix_tz_opt(elem.attrib.get("creationDate")),
    )


def extract_walking_metric(elem: Element, hk_type: str) -> WalkingMetricRow:
    """Extract a walking metric record with a metric discriminator."""
    metric = WALKING_METRIC_TYPES[hk_type]
    return (
        elem.attrib["sourceName"],
        elem.attrib.get("sourceVersion"),
        metric,
        elem.attrib["unit"],
        float(elem.attrib["value"]),
        _fix_tz(elem.attrib["startDate"]),
        _fix_tz(elem.attrib["endDate"]),
        _fix_tz_opt(elem.attrib.get("creationDate")),
    )


def classify_and_extract(elem: Element) -> tuple[str, tuple[object, ...]] | None:
    """Classify a Record element and extract its data.

    Returns (table_name, row_tuple) or None if the record type is unrecognized.
    """
    hk_type = elem.attrib.get("type", "")
    table = TYPE_REGISTRY.get(hk_type)
    if table is None:
        return None

    if table == "sleep_sessions":
        return table, extract_sleep_record(elem)
    if table == "body_measurements":
        return table, extract_body_measurement(elem, hk_type)
    if table == "walking_metrics":
        return table, extract_walking_metric(elem, hk_type)
    return table, extract_quantity_record(elem)


# PyArrow schemas for each table shape
_QUANTITY_SCHEMA = pa.schema([
    ("source_name", pa.string()),
    ("source_version", pa.string()),
    ("unit", pa.string()),
    ("value", pa.float64()),
    ("start_date", pa.string()),
    ("end_date", pa.string()),
    ("creation_date", pa.string()),
])

_SLEEP_SCHEMA = pa.schema([
    ("source_name", pa.string()),
    ("source_version", pa.string()),
    ("stage", pa.string()),
    ("start_date", pa.string()),
    ("end_date", pa.string()),
    ("creation_date", pa.string()),
])

_WORKOUT_SCHEMA = pa.schema([
    ("workout_type", pa.string()),
    ("source_name", pa.string()),
    ("source_version", pa.string()),
    ("duration", pa.float64()),
    ("total_distance", pa.float64()),
    ("total_energy", pa.float64()),
    ("start_date", pa.string()),
    ("end_date", pa.string()),
    ("creation_date", pa.string()),
])

_ACTIVITY_SUMMARY_SCHEMA = pa.schema([
    ("date", pa.string()),
    ("active_energy", pa.float64()),
    ("active_energy_goal", pa.float64()),
    ("exercise_minutes", pa.float64()),
    ("exercise_goal", pa.float64()),
    ("stand_hours", pa.float64()),
    ("stand_goal", pa.float64()),
])

_BODY_MEASUREMENT_SCHEMA = pa.schema([
    ("source_name", pa.string()),
    ("source_version", pa.string()),
    ("measurement", pa.string()),
    ("unit", pa.string()),
    ("value", pa.float64()),
    ("start_date", pa.string()),
    ("end_date", pa.string()),
    ("creation_date", pa.string()),
])

_WALKING_METRIC_SCHEMA = pa.schema([
    ("source_name", pa.string()),
    ("source_version", pa.string()),
    ("metric", pa.string()),
    ("unit", pa.string()),
    ("value", pa.float64()),
    ("start_date", pa.string()),
    ("end_date", pa.string()),
    ("creation_date", pa.string()),
])

_TABLE_SCHEMAS: dict[str, pa.Schema] = {
    "step_counts": _QUANTITY_SCHEMA,
    "heart_rate_samples": _QUANTITY_SCHEMA,
    "resting_heart_rate": _QUANTITY_SCHEMA,
    "hrv_samples": _QUANTITY_SCHEMA,
    "vo2_max": _QUANTITY_SCHEMA,
    "active_energy": _QUANTITY_SCHEMA,
    "basal_energy": _QUANTITY_SCHEMA,
    "distance_walking_running": _QUANTITY_SCHEMA,
    "respiratory_rate": _QUANTITY_SCHEMA,
    "oxygen_saturation": _QUANTITY_SCHEMA,
    "sleep_sessions": _SLEEP_SCHEMA,
    "walking_metrics": _WALKING_METRIC_SCHEMA,
    "body_measurements": _BODY_MEASUREMENT_SCHEMA,
    "workouts": _WORKOUT_SCHEMA,
    "activity_summary": _ACTIVITY_SUMMARY_SCHEMA,
}


def flush_batch(
    conn: _duckdb.DuckDBPyConnection,
    table_name: str,
    rows: list[tuple[object, ...]],
) -> None:
    """Flush a batch of rows to DuckDB via PyArrow."""
    if not rows:
        return
    schema = _TABLE_SCHEMAS[table_name]
    # Transpose rows into columnar arrays
    num_cols = len(schema)
    columns: list[list[object]] = [[] for _ in range(num_cols)]
    for row in rows:
        for i, val in enumerate(row):
            columns[i].append(val)
    arrow_arrays: list[pa.Array[pa.Scalar[object]]] = [  # pyright: ignore[reportInvalidTypeArguments]
        pa.array(col, type=schema.field(i).type)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        for i, col in enumerate(columns)
    ]
    batch = pa.table(arrow_arrays, schema=schema)  # pyright: ignore[reportUnknownMemberType]
    # DuckDB can query PyArrow tables directly when registered
    conn.register("_batch", batch)
    conn.sql(f"INSERT INTO {table_name} SELECT * FROM _batch")
    conn.unregister("_batch")


def parse_export(
    conn: _duckdb.DuckDBPyConnection,
    xml_path: Path,
    *,
    type_filter: set[str] | None = None,
    since: str | None = None,
    batch_size: int = 50_000,
) -> tuple[dict[str, int], str | None]:
    """Stream-parse an Apple Health export.xml and ingest into DuckDB.

    Returns (stats_dict, date_of_birth). stats_dict maps table_name -> row_count,
    plus 'total', 'skipped', 'errors'. date_of_birth is from the <Me> element or None.
    """
    batches: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    stats: dict[str, int] = defaultdict(int)
    processed = 0
    date_of_birth: str | None = None

    context = iterparse(str(xml_path), events=("end",))

    for _event, elem in context:
        tag = elem.tag

        if tag == "Record":
            result = _process_record(elem, type_filter, since)
            if result is None:
                stats["skipped"] += 1
            else:
                table_name, row = result
                batches[table_name].append(row)
                stats[table_name] = stats.get(table_name, 0) + 1
        elif tag == "Workout":
            if since and elem.attrib.get("startDate", "") < since:
                stats["skipped"] += 1
            elif type_filter and "workouts" not in type_filter:
                stats["skipped"] += 1
            else:
                row = extract_workout(elem)
                batches["workouts"].append(row)
                stats["workouts"] = stats.get("workouts", 0) + 1
        elif tag == "ActivitySummary":
            if since and elem.attrib.get("dateComponents", "") < since:
                stats["skipped"] += 1
            elif type_filter and "activity_summary" not in type_filter:
                stats["skipped"] += 1
            else:
                row = extract_activity_summary(elem)
                batches["activity_summary"].append(row)
                stats["activity_summary"] = stats.get("activity_summary", 0) + 1
        elif tag == "Me":
            dob = elem.attrib.get("HKCharacteristicTypeIdentifierDateOfBirth")
            if dob:
                date_of_birth = dob
            elem.clear()
            continue
        else:
            elem.clear()
            continue

        # Flush any batch that hit the threshold
        for table_name in list(batches.keys()):
            if len(batches[table_name]) >= batch_size:
                flush_batch(conn, table_name, batches[table_name])
                batches[table_name] = []

        # Memory cleanup
        elem.clear()
        processed += 1
        if processed % 100_000 == 0:
            print(f"  processed {processed:,} elements...", file=sys.stderr)

    # Flush remaining batches
    for table_name, rows in batches.items():
        if rows:
            flush_batch(conn, table_name, rows)

    stats["total"] = sum(v for k, v in stats.items() if k not in ("skipped", "errors", "total"))
    return dict(stats), date_of_birth


def _estimate_max_hr(date_of_birth: str) -> int:
    """Estimate max HR using Tanaka formula: 208 - 0.7 * age."""
    from datetime import date

    birth = date.fromisoformat(date_of_birth)
    today = date.today()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    return int(208 - 0.7 * age)


def compute_hr_zones(
    conn: _duckdb.DuckDBPyConnection,
    max_hr: int | None = None,
    date_of_birth: str | None = None,
) -> int:
    """Compute HR zones for each workout from overlapping heart_rate_samples.

    Uses max_hr if provided, otherwise estimates from date_of_birth.
    Returns the number of zone rows inserted.
    """
    if max_hr is None and date_of_birth is not None:
        max_hr = _estimate_max_hr(date_of_birth)
    if max_hr is None:
        print("  hr zones: skipped (no --max-hr and no date of birth in export)", file=sys.stderr)
        return 0

    conn.sql(f"""
        INSERT INTO workout_hr_zones
        SELECT
            workout_start,
            workout_type,
            CASE
                WHEN hr < {max_hr} * 0.6 THEN 1
                WHEN hr < {max_hr} * 0.7 THEN 2
                WHEN hr < {max_hr} * 0.8 THEN 3
                WHEN hr < {max_hr} * 0.9 THEN 4
                ELSE 5
            END AS zone,
            SUM(sample_seconds) AS seconds,
            source_name
        FROM (
            SELECT
                w.start_date AS workout_start,
                w.workout_type,
                w.source_name,
                h.value AS hr,
                EXTRACT(EPOCH FROM (
                    h.end_date::TIMESTAMP - h.start_date::TIMESTAMP
                )) AS sample_seconds
            FROM workouts w
            JOIN heart_rate_samples h
                ON h.start_date >= w.start_date
                AND h.start_date < w.end_date
            WHERE EXTRACT(EPOCH FROM (
                h.end_date::TIMESTAMP - h.start_date::TIMESTAMP
            )) > 0
        ) sub
        GROUP BY workout_start, workout_type, zone, source_name
    """)

    count_row = conn.sql("SELECT COUNT(*) FROM workout_hr_zones").fetchone()
    count: int = count_row[0] if count_row else 0
    print(f"  hr zones: {count} rows (max HR = {max_hr} bpm)", file=sys.stderr)
    return count


def _process_record(
    elem: Element,
    type_filter: set[str] | None,
    since: str | None,
) -> tuple[str, tuple[object, ...]] | None:
    """Process a Record element. Returns (table, row) or None to skip."""
    # Date filter (string comparison works for ISO-ish dates with same format)
    if since and elem.attrib.get("startDate", "") < since:
        return None

    result = classify_and_extract(elem)
    if result is None:
        return None

    table_name, row = result
    if type_filter and table_name not in type_filter:
        return None

    return table_name, row
