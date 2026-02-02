"""DuckDB table definitions, type registry, and view creation."""

import duckdb

TYPE_REGISTRY: dict[str, str] = {
    "HKQuantityTypeIdentifierStepCount": "step_counts",
    "HKQuantityTypeIdentifierHeartRate": "heart_rate_samples",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_heart_rate",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_samples",
    "HKQuantityTypeIdentifierVO2Max": "vo2_max",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy",
    "HKQuantityTypeIdentifierBasalEnergyBurned": "basal_energy",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance_walking_running",
    "HKQuantityTypeIdentifierBodyMass": "body_measurements",
    "HKQuantityTypeIdentifierHeight": "body_measurements",
    "HKQuantityTypeIdentifierBodyFatPercentage": "body_measurements",
    "HKQuantityTypeIdentifierRespiratoryRate": "respiratory_rate",
    "HKQuantityTypeIdentifierOxygenSaturation": "oxygen_saturation",
    "HKQuantityTypeIdentifierWalkingSpeed": "walking_metrics",
    "HKQuantityTypeIdentifierWalkingStepLength": "walking_metrics",
    "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage": "walking_metrics",
    "HKQuantityTypeIdentifierWalkingAsymmetryPercentage": "walking_metrics",
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep_sessions",
}

SLEEP_STAGES: dict[str, str] = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAwake": "awake",
}

BODY_MEASUREMENT_TYPES: dict[str, str] = {
    "HKQuantityTypeIdentifierBodyMass": "body_mass",
    "HKQuantityTypeIdentifierHeight": "height",
    "HKQuantityTypeIdentifierBodyFatPercentage": "body_fat",
}

WALKING_METRIC_TYPES: dict[str, str] = {
    "HKQuantityTypeIdentifierWalkingSpeed": "speed",
    "HKQuantityTypeIdentifierWalkingStepLength": "step_length",
    "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage": "double_support",
    "HKQuantityTypeIdentifierWalkingAsymmetryPercentage": "asymmetry",
}

TABLE_NAMES: frozenset[str] = frozenset({
    "step_counts",
    "heart_rate_samples",
    "resting_heart_rate",
    "hrv_samples",
    "vo2_max",
    "active_energy",
    "basal_energy",
    "distance_walking_running",
    "body_measurements",
    "walking_metrics",
    "sleep_sessions",
    "respiratory_rate",
    "oxygen_saturation",
    "workouts",
    "activity_summary",
    "clinical_labs",
})


def table_for_record_type(hk_type: str) -> str | None:
    """Return the target table name for an Apple Health record type, or None if unknown."""
    return TYPE_REGISTRY.get(hk_type)


# Column definitions for the "standard" quantity table shape
_QUANTITY_COLS = """
    source_name     VARCHAR NOT NULL,
    source_version  VARCHAR,
    unit            VARCHAR NOT NULL,
    value           DOUBLE NOT NULL,
    start_date      TIMESTAMPTZ NOT NULL,
    end_date        TIMESTAMPTZ NOT NULL,
    creation_date   TIMESTAMPTZ
"""

_TABLE_DDL: dict[str, str] = {
    "step_counts": f"CREATE TABLE IF NOT EXISTS step_counts ({_QUANTITY_COLS})",
    "heart_rate_samples": f"CREATE TABLE IF NOT EXISTS heart_rate_samples ({_QUANTITY_COLS})",
    "resting_heart_rate": f"CREATE TABLE IF NOT EXISTS resting_heart_rate ({_QUANTITY_COLS})",
    "hrv_samples": f"CREATE TABLE IF NOT EXISTS hrv_samples ({_QUANTITY_COLS})",
    "vo2_max": f"CREATE TABLE IF NOT EXISTS vo2_max ({_QUANTITY_COLS})",
    "active_energy": f"CREATE TABLE IF NOT EXISTS active_energy ({_QUANTITY_COLS})",
    "basal_energy": f"CREATE TABLE IF NOT EXISTS basal_energy ({_QUANTITY_COLS})",
    "distance_walking_running": (
        f"CREATE TABLE IF NOT EXISTS distance_walking_running ({_QUANTITY_COLS})"
    ),
    "respiratory_rate": f"CREATE TABLE IF NOT EXISTS respiratory_rate ({_QUANTITY_COLS})",
    "oxygen_saturation": f"CREATE TABLE IF NOT EXISTS oxygen_saturation ({_QUANTITY_COLS})",
    "sleep_sessions": """CREATE TABLE IF NOT EXISTS sleep_sessions (
        source_name     VARCHAR NOT NULL,
        source_version  VARCHAR,
        stage           VARCHAR NOT NULL,
        start_date      TIMESTAMPTZ NOT NULL,
        end_date        TIMESTAMPTZ NOT NULL,
        creation_date   TIMESTAMPTZ
    )""",
    "walking_metrics": """CREATE TABLE IF NOT EXISTS walking_metrics (
        source_name     VARCHAR NOT NULL,
        source_version  VARCHAR,
        metric          VARCHAR NOT NULL,
        unit            VARCHAR NOT NULL,
        value           DOUBLE NOT NULL,
        start_date      TIMESTAMPTZ NOT NULL,
        end_date        TIMESTAMPTZ NOT NULL,
        creation_date   TIMESTAMPTZ
    )""",
    "body_measurements": """CREATE TABLE IF NOT EXISTS body_measurements (
        source_name     VARCHAR NOT NULL,
        source_version  VARCHAR,
        measurement     VARCHAR NOT NULL,
        unit            VARCHAR NOT NULL,
        value           DOUBLE NOT NULL,
        start_date      TIMESTAMPTZ NOT NULL,
        end_date        TIMESTAMPTZ NOT NULL,
        creation_date   TIMESTAMPTZ
    )""",
    "workouts": """CREATE TABLE IF NOT EXISTS workouts (
        workout_type    VARCHAR NOT NULL,
        source_name     VARCHAR NOT NULL,
        source_version  VARCHAR,
        duration        DOUBLE,
        total_distance  DOUBLE,
        total_energy    DOUBLE,
        start_date      TIMESTAMPTZ NOT NULL,
        end_date        TIMESTAMPTZ NOT NULL,
        creation_date   TIMESTAMPTZ
    )""",
    "activity_summary": """CREATE TABLE IF NOT EXISTS activity_summary (
        date                DATE NOT NULL UNIQUE,
        active_energy       DOUBLE,
        active_energy_goal  DOUBLE,
        exercise_minutes    DOUBLE,
        exercise_goal       DOUBLE,
        stand_hours         DOUBLE,
        stand_goal          DOUBLE
    )""",
    "clinical_labs": """CREATE TABLE IF NOT EXISTS clinical_labs (
        date              DATE NOT NULL,
        test              VARCHAR NOT NULL,
        value             DOUBLE NOT NULL,
        unit              VARCHAR,
        ref_low           DOUBLE,
        ref_high          DOUBLE,
        longevity_target  VARCHAR,
        optimal           VARCHAR
    )""",
}


def create_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all health data tables if they don't exist."""
    for ddl in _TABLE_DDL.values():
        conn.sql(ddl)


def truncate_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Truncate all health data tables."""
    for table_name in _TABLE_DDL:
        conn.sql(f"TRUNCATE TABLE {table_name}")


_VIEW_SQL: list[str] = [
    """CREATE OR REPLACE VIEW daily_steps AS
    SELECT start_date::DATE AS date, SUM(value) AS total_steps
    FROM step_counts GROUP BY 1""",

    """CREATE OR REPLACE VIEW daily_heart_rate AS
    SELECT start_date::DATE AS date,
           MIN(value) AS min_bpm, AVG(value) AS avg_bpm, MAX(value) AS max_bpm,
           COUNT(*) AS sample_count
    FROM heart_rate_samples GROUP BY 1""",

    """CREATE OR REPLACE VIEW hrv_trends AS
    WITH daily AS (
        SELECT start_date::DATE AS date, AVG(value) AS daily_avg_ms
        FROM hrv_samples GROUP BY 1
    )
    SELECT date, daily_avg_ms,
        AVG(daily_avg_ms) OVER (
            ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d,
        AVG(daily_avg_ms) OVER (
            ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS rolling_30d
    FROM daily""",

    """CREATE OR REPLACE VIEW sleep_sessions_summary AS
    SELECT
        MIN(start_date)::DATE AS night_of,
        MIN(start_date) AS sleep_onset,
        MAX(end_date) AS wake_time,
        SUM(EXTRACT(EPOCH FROM (end_date - start_date)))
            FILTER (WHERE stage != 'in_bed') AS total_sleep_seconds,
        SUM(EXTRACT(EPOCH FROM (end_date - start_date)))
            FILTER (WHERE stage = 'in_bed') AS total_in_bed_seconds,
        SUM(EXTRACT(EPOCH FROM (end_date - start_date)))
            FILTER (WHERE stage = 'deep') AS deep_seconds,
        SUM(EXTRACT(EPOCH FROM (end_date - start_date)))
            FILTER (WHERE stage = 'rem') AS rem_seconds
    FROM sleep_sessions
    GROUP BY start_date::DATE""",

    """CREATE OR REPLACE VIEW daily_sleep AS
    SELECT start_date::DATE AS date, stage,
        SUM(EXTRACT(EPOCH FROM (end_date - start_date))) AS total_seconds
    FROM sleep_sessions GROUP BY 1, 2""",

    """CREATE OR REPLACE VIEW daily_energy AS
    SELECT COALESCE(a.date, b.date) AS date,
        a.total_kcal AS active_kcal, b.total_kcal AS basal_kcal
    FROM (SELECT start_date::DATE AS date, SUM(value) AS total_kcal FROM active_energy GROUP BY 1) a
    FULL OUTER JOIN
        (SELECT start_date::DATE AS date, SUM(value) AS total_kcal FROM basal_energy GROUP BY 1) b
    ON a.date = b.date""",

    """CREATE OR REPLACE VIEW daily_distance AS
    SELECT start_date::DATE AS date, SUM(value) AS total_distance, MIN(unit) AS unit
    FROM distance_walking_running GROUP BY 1""",

    """CREATE OR REPLACE VIEW vo2_max_trend AS
    SELECT start_date::DATE AS date, value AS vo2_max
    FROM vo2_max ORDER BY 1""",

    """CREATE OR REPLACE VIEW body_composition_trend AS
    SELECT start_date::DATE AS date, measurement, value,
        AVG(value) OVER (
            PARTITION BY measurement ORDER BY start_date::DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d_avg
    FROM body_measurements""",

    # ── Dashboard views ──────────────────────────────────────────

    """CREATE OR REPLACE VIEW dashboard_steps AS
    WITH daily AS (
        SELECT start_date::DATE AS date, SUM(value) AS total_steps
        FROM step_counts GROUP BY 1
    )
    SELECT date, total_steps,
        AVG(total_steps) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS r7,
        AVG(total_steps) OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS r30
    FROM daily ORDER BY date""",

    """CREATE OR REPLACE VIEW dashboard_sleep AS
    SELECT
        night_of AS date,
        total_sleep_seconds / 3600.0 AS total,
        deep_seconds / 3600.0 AS deep,
        rem_seconds / 3600.0 AS rem
    FROM sleep_sessions_summary ORDER BY night_of""",

    """CREATE OR REPLACE VIEW dashboard_rhr AS
    SELECT start_date::DATE AS date, MIN(value) AS v
    FROM resting_heart_rate GROUP BY 1 ORDER BY 1""",

    """CREATE OR REPLACE VIEW dashboard_hrv AS
    SELECT date, daily_avg_ms AS v, rolling_7d AS r7, rolling_30d AS r30
    FROM hrv_trends ORDER BY date""",

    """CREATE OR REPLACE VIEW dashboard_spo2 AS
    SELECT start_date::DATE AS date,
        MIN(value * 100) AS min,
        AVG(value * 100) AS avg
    FROM oxygen_saturation GROUP BY 1 ORDER BY 1""",

    """CREATE OR REPLACE VIEW dashboard_vo2 AS
    SELECT date, vo2_max AS v FROM vo2_max_trend ORDER BY date""",

    """CREATE OR REPLACE VIEW dashboard_bodyfat AS
    SELECT start_date::DATE AS date, value AS v
    FROM body_measurements WHERE measurement = 'body_fat' ORDER BY 1""",

    """CREATE OR REPLACE VIEW dashboard_weight AS
    SELECT start_date::DATE AS date,
        CASE WHEN unit = 'kg' THEN value * 2.20462 ELSE value END AS v
    FROM body_measurements WHERE measurement = 'body_mass' ORDER BY 1""",

    """CREATE OR REPLACE VIEW dashboard_exercise AS
    SELECT DATE_TRUNC('week', date)::DATE AS date,
        SUM(exercise_minutes) AS v
    FROM activity_summary GROUP BY 1 ORDER BY 1""",

    """CREATE OR REPLACE VIEW dashboard_hrzones AS
    SELECT DATE_TRUNC('week', start_date)::DATE AS date,
        SUM(duration / 60.0 * 0.4) AS z2,
        SUM(duration / 60.0 * 0.1) AS z4
    FROM workouts GROUP BY 1 ORDER BY 1""",

    """CREATE OR REPLACE VIEW dashboard_scorecard AS
    WITH steps AS (SELECT date, total_steps AS steps FROM dashboard_steps),
         sleep AS (SELECT date, total, deep, rem FROM dashboard_sleep),
         rhr AS (SELECT date, v AS hr FROM dashboard_rhr),
         hrv AS (SELECT date, v AS hrv FROM dashboard_hrv),
         spo2 AS (SELECT date, min AS spo2_min, avg AS spo2_avg FROM dashboard_spo2)
    SELECT COALESCE(steps.date, sleep.date, rhr.date, hrv.date, spo2.date) AS date,
        steps.steps, sleep.total AS sleep, sleep.deep, sleep.rem,
        rhr.hr, hrv.hrv, spo2.spo2_min, spo2.spo2_avg
    FROM steps
    FULL OUTER JOIN sleep ON steps.date = sleep.date
    FULL OUTER JOIN rhr ON COALESCE(steps.date, sleep.date) = rhr.date
    FULL OUTER JOIN hrv ON COALESCE(steps.date, sleep.date, rhr.date) = hrv.date
    FULL OUTER JOIN spo2 ON COALESCE(steps.date, sleep.date, rhr.date, hrv.date) = spo2.date
    ORDER BY 1""",

    """CREATE OR REPLACE VIEW dashboard_labs AS
    SELECT date, test, value, unit, longevity_target, optimal
    FROM clinical_labs ORDER BY date DESC, test""",
]


def create_views(conn: duckdb.DuckDBPyConnection) -> None:
    """Create or replace all pre-aggregated views."""
    for sql in _VIEW_SQL:
        conn.sql(sql)
