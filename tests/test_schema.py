"""Tests for schema module."""

import duckdb

from mosaic.schema import (
    BODY_MEASUREMENT_TYPES,
    SLEEP_STAGES,
    TABLE_NAMES,
    TYPE_REGISTRY,
    WALKING_METRIC_TYPES,
    create_tables,
    create_views,
    table_for_record_type,
    truncate_tables,
)


class TestTypeRegistry:
    def test_step_count_maps_to_step_counts(self) -> None:
        assert TYPE_REGISTRY["HKQuantityTypeIdentifierStepCount"] == "step_counts"

    def test_sleep_maps_to_sleep_sessions(self) -> None:
        assert TYPE_REGISTRY["HKCategoryTypeIdentifierSleepAnalysis"] == "sleep_sessions"

    def test_all_registry_values_are_valid_table_names(self) -> None:
        for hk_type, table in TYPE_REGISTRY.items():
            assert table in TABLE_NAMES, f"{hk_type} maps to unknown table {table}"

    def test_table_for_record_type_known(self) -> None:
        assert table_for_record_type("HKQuantityTypeIdentifierHeartRate") == "heart_rate_samples"

    def test_table_for_record_type_unknown_returns_none(self) -> None:
        assert table_for_record_type("HKQuantityTypeIdentifierBloodPressure") is None


class TestSleepStages:
    def test_in_bed(self) -> None:
        assert SLEEP_STAGES["HKCategoryValueSleepAnalysisInBed"] == "in_bed"

    def test_all_stages_are_strings(self) -> None:
        for hk_val, stage in SLEEP_STAGES.items():
            assert isinstance(stage, str), f"{hk_val} maps to non-string {stage}"


class TestBodyMeasurementTypes:
    def test_body_mass(self) -> None:
        assert BODY_MEASUREMENT_TYPES["HKQuantityTypeIdentifierBodyMass"] == "body_mass"


class TestWalkingMetricTypes:
    def test_walking_speed(self) -> None:
        assert WALKING_METRIC_TYPES["HKQuantityTypeIdentifierWalkingSpeed"] == "speed"


class TestCreateTables:
    def test_creates_step_counts_table(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        result = db.sql("SELECT * FROM step_counts LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "source_name" in col_names
        assert "value" in col_names
        assert "start_date" in col_names

    def test_creates_sleep_sessions_table(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        result = db.sql("SELECT * FROM sleep_sessions LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "stage" in col_names
        assert "start_date" in col_names

    def test_creates_workouts_table(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        result = db.sql("SELECT * FROM workouts LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "workout_type" in col_names
        assert "duration" in col_names

    def test_creates_activity_summary_table(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        result = db.sql("SELECT * FROM activity_summary LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "date" in col_names
        assert "active_energy" in col_names

    def test_creates_walking_metrics_table(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        result = db.sql("SELECT * FROM walking_metrics LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "metric" in col_names

    def test_creates_body_measurements_table(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        result = db.sql("SELECT * FROM body_measurements LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "measurement" in col_names

    def test_idempotent(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_tables(db)  # should not raise

    def test_creates_all_tables(self, db: duckdb.DuckDBPyConnection) -> None:
        from mosaic.schema import TABLE_NAMES

        create_tables(db)
        result = db.sql("SHOW TABLES").fetchall()
        created = {row[0] for row in result}
        assert TABLE_NAMES <= created


class TestTruncateTables:
    def test_truncate_clears_data(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO step_counts VALUES
            ('Watch', '10', 'count', 100.0,
             '2024-01-01 08:00:00-06', '2024-01-01 08:01:00-06',
             '2024-01-01 08:01:00-06')
        """)
        assert db.sql("SELECT COUNT(*) FROM step_counts").fetchone()[0] == 1
        truncate_tables(db)
        assert db.sql("SELECT COUNT(*) FROM step_counts").fetchone()[0] == 0


class TestCreateViews:
    def test_creates_daily_steps_view(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        # Should be queryable (empty is fine)
        result = db.sql("SELECT * FROM daily_steps LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "date" in col_names
        assert "total_steps" in col_names

    def test_creates_hrv_trends_view(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        result = db.sql("SELECT * FROM hrv_trends LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "rolling_7d" in col_names
        assert "rolling_30d" in col_names

    def test_creates_sleep_sessions_summary_view(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        result = db.sql("SELECT * FROM sleep_sessions_summary LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "night_of" in col_names
        assert "deep_seconds" in col_names

    def test_creates_all_views(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        for view_name in [
            "daily_steps", "daily_heart_rate", "hrv_trends",
            "sleep_sessions_summary", "daily_sleep", "daily_energy",
            "daily_distance", "vo2_max_trend", "body_composition_trend",
            "dashboard_steps", "dashboard_sleep", "dashboard_rhr",
            "dashboard_hrv", "dashboard_spo2", "dashboard_vo2",
            "dashboard_bodyfat", "dashboard_weight", "dashboard_exercise",
            "dashboard_hrzones", "dashboard_scorecard", "dashboard_labs",
        ]:
            db.sql(f"SELECT * FROM {view_name} LIMIT 0")  # should not raise

    def test_idempotent(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        create_views(db)  # should not raise


class TestClinicalLabsTable:
    def test_creates_clinical_labs_table(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        result = db.sql("SELECT * FROM clinical_labs LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "date" in col_names
        assert "test" in col_names
        assert "value" in col_names
        assert "optimal" in col_names

    def test_clinical_labs_in_table_names(self) -> None:
        assert "clinical_labs" in TABLE_NAMES


class TestDashboardViews:
    def test_dashboard_steps_columns(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        cols = [c[0] for c in db.sql("SELECT * FROM dashboard_steps LIMIT 0").description]
        assert set(cols) == {"date", "total_steps", "r7", "r30"}

    def test_dashboard_sleep_columns(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        cols = [c[0] for c in db.sql("SELECT * FROM dashboard_sleep LIMIT 0").description]
        assert set(cols) == {"date", "total", "deep", "rem"}

    def test_dashboard_spo2_columns(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        cols = [c[0] for c in db.sql("SELECT * FROM dashboard_spo2 LIMIT 0").description]
        assert set(cols) == {"date", "min", "avg"}

    def test_dashboard_scorecard_columns(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        cols = [c[0] for c in db.sql("SELECT * FROM dashboard_scorecard LIMIT 0").description]
        expected = {"date", "steps", "sleep", "deep", "rem", "hr", "hrv", "spo2_min", "spo2_avg"}
        assert expected == set(cols)

    def test_dashboard_steps_with_data(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        for i in range(5):
            db.sql(f"""
                INSERT INTO step_counts VALUES
                ('Watch', '10', 'count', {1000 + i * 100},
                 '2024-01-0{i+1} 08:00:00-06', '2024-01-0{i+1} 08:01:00-06',
                 '2024-01-0{i+1} 08:01:00-06')
            """)
        create_views(db)
        rows = db.sql("SELECT * FROM dashboard_steps").fetchall()
        assert len(rows) == 5
        # r7 and r30 should be non-null
        assert all(r[2] is not None for r in rows)
        assert all(r[3] is not None for r in rows)

    def test_dashboard_labs_with_data(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO clinical_labs VALUES
            ('2024-01-30', 'Glucose', 79.0, 'mg/dL', 70, 99, '<90', '72-85')
        """)
        create_views(db)
        rows = db.sql("SELECT * FROM dashboard_labs").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "Glucose"
