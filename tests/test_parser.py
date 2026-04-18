"""Tests for the XML parser module."""

from pathlib import Path
from xml.etree.ElementTree import fromstring

import duckdb

from mosaic.parser import (
    classify_and_extract,
    compute_hr_zones,
    extract_body_measurement,
    extract_quantity_record,
    extract_sleep_record,
    extract_walking_metric,
    extract_workout,
    flush_batch,
    parse_export,
)
from mosaic.schema import create_tables

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestExtractQuantityRecord:
    def test_extracts_step_count(self) -> None:
        xml = """<Record type="HKQuantityTypeIdentifierStepCount"
            sourceName="Apple Watch" sourceVersion="10.3"
            unit="count" value="45"
            startDate="2024-03-15 08:30:00 -0600"
            endDate="2024-03-15 08:31:00 -0600"
            creationDate="2024-03-15 08:31:05 -0600"/>"""
        elem = fromstring(xml)
        result = extract_quantity_record(elem)
        assert result == (
            "Apple Watch", "10.3", "count", 45.0,
            "2024-03-15 08:30:00-06:00",
            "2024-03-15 08:31:00-06:00",
            "2024-03-15 08:31:05-06:00",
        )

    def test_missing_source_version_is_none(self) -> None:
        xml = """<Record type="HKQuantityTypeIdentifierStepCount"
            sourceName="Watch" unit="count" value="10"
            startDate="2024-03-15 08:30:00 -0600"
            endDate="2024-03-15 08:31:00 -0600"/>"""
        elem = fromstring(xml)
        result = extract_quantity_record(elem)
        assert result[1] is None  # source_version
        assert result[6] is None  # creation_date


class TestExtractSleepRecord:
    def test_extracts_deep_sleep(self) -> None:
        xml = """<Record type="HKCategoryTypeIdentifierSleepAnalysis"
            sourceName="Apple Watch" sourceVersion="10.3"
            value="HKCategoryValueSleepAnalysisAsleepDeep"
            startDate="2024-03-14 23:30:00 -0600"
            endDate="2024-03-15 00:15:00 -0600"
            creationDate="2024-03-15 06:00:00 -0600"/>"""
        elem = fromstring(xml)
        result = extract_sleep_record(elem)
        assert result == (
            "Apple Watch", "10.3", "deep",
            "2024-03-14 23:30:00-06:00",
            "2024-03-15 00:15:00-06:00",
            "2024-03-15 06:00:00-06:00",
        )

    def test_unknown_sleep_stage_uses_raw_value(self) -> None:
        xml = """<Record type="HKCategoryTypeIdentifierSleepAnalysis"
            sourceName="Watch" sourceVersion="10"
            value="HKCategoryValueSleepAnalysisSomethingNew"
            startDate="2024-01-01 00:00:00 -0600"
            endDate="2024-01-01 01:00:00 -0600"/>"""
        elem = fromstring(xml)
        result = extract_sleep_record(elem)
        assert result[2] == "HKCategoryValueSleepAnalysisSomethingNew"


class TestExtractWorkout:
    def test_extracts_running_workout(self) -> None:
        xml = """<Workout workoutActivityType="HKWorkoutActivityTypeRunning"
            duration="30.5" durationUnit="min"
            totalDistance="5.2" totalDistanceUnit="km"
            totalEnergyBurned="320" totalEnergyBurnedUnit="kcal"
            sourceName="Apple Watch" sourceVersion="10.3"
            startDate="2024-03-15 09:00:00 -0600"
            endDate="2024-03-15 09:30:30 -0600"
            creationDate="2024-03-15 09:31:00 -0600"/>"""
        elem = fromstring(xml)
        result = extract_workout(elem)
        assert result[0] == "running"
        assert result[1] == "Apple Watch"
        assert result[3] == 30.5  # duration
        assert result[4] == 5.2   # distance
        assert result[5] == 320.0 # energy

    def test_hiit_workout_type_normalized(self) -> None:
        xml = """<Workout workoutActivityType="HKWorkoutActivityTypeHighIntensityIntervalTraining"
            duration="20" sourceName="Watch" sourceVersion="10"
            startDate="2024-03-15 09:00:00 -0600"
            endDate="2024-03-15 09:20:00 -0600"/>"""
        elem = fromstring(xml)
        result = extract_workout(elem)
        assert result[0] == "high_intensity_interval_training"


class TestExtractBodyMeasurement:
    def test_body_mass(self) -> None:
        xml = """<Record type="HKQuantityTypeIdentifierBodyMass"
            sourceName="Health" sourceVersion="17.0"
            unit="lb" value="155"
            startDate="2024-03-15 07:00:00 -0600"
            endDate="2024-03-15 07:00:00 -0600"
            creationDate="2024-03-15 07:00:05 -0600"/>"""
        elem = fromstring(xml)
        result = extract_body_measurement(elem, "HKQuantityTypeIdentifierBodyMass")
        assert result[2] == "body_mass"  # measurement discriminator
        assert result[4] == 155.0


class TestExtractWalkingMetric:
    def test_walking_speed(self) -> None:
        xml = """<Record type="HKQuantityTypeIdentifierWalkingSpeed"
            sourceName="Apple Watch" sourceVersion="10.3"
            unit="mi/hr" value="3.2"
            startDate="2024-03-15 08:30:00 -0600"
            endDate="2024-03-15 08:31:00 -0600"
            creationDate="2024-03-15 08:31:05 -0600"/>"""
        elem = fromstring(xml)
        result = extract_walking_metric(elem, "HKQuantityTypeIdentifierWalkingSpeed")
        assert result[2] == "speed"  # metric discriminator
        assert result[4] == 3.2


class TestClassifyAndExtract:
    def test_step_count_returns_table_and_row(self) -> None:
        xml = """<Record type="HKQuantityTypeIdentifierStepCount"
            sourceName="Watch" sourceVersion="10" unit="count" value="100"
            startDate="2024-01-01 08:00:00 -0600"
            endDate="2024-01-01 08:01:00 -0600"/>"""
        elem = fromstring(xml)
        table, row = classify_and_extract(elem)
        assert table == "step_counts"
        assert row[3] == 100.0

    def test_sleep_returns_table_and_row(self) -> None:
        xml = """<Record type="HKCategoryTypeIdentifierSleepAnalysis"
            sourceName="Watch" sourceVersion="10"
            value="HKCategoryValueSleepAnalysisAsleepREM"
            startDate="2024-01-01 00:00:00 -0600"
            endDate="2024-01-01 01:00:00 -0600"/>"""
        elem = fromstring(xml)
        table, row = classify_and_extract(elem)
        assert table == "sleep_sessions"
        assert row[2] == "rem"

    def test_body_mass_returns_body_measurements(self) -> None:
        xml = """<Record type="HKQuantityTypeIdentifierBodyMass"
            sourceName="Health" sourceVersion="17" unit="lb" value="155"
            startDate="2024-01-01 07:00:00 -0600"
            endDate="2024-01-01 07:00:00 -0600"/>"""
        elem = fromstring(xml)
        table, row = classify_and_extract(elem)
        assert table == "body_measurements"
        assert row[2] == "body_mass"

    def test_unknown_type_returns_none(self) -> None:
        xml = """<Record type="HKQuantityTypeIdentifierBloodPressure"
            sourceName="Omron" unit="mmHg" value="120"
            startDate="2024-01-01 07:00:00 -0600"
            endDate="2024-01-01 07:00:00 -0600"/>"""
        elem = fromstring(xml)
        result = classify_and_extract(elem)
        assert result is None


class TestFlushBatch:
    def test_flush_step_counts(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        rows: list[tuple[object, ...]] = [
            ("Watch", "10", "count", 45.0,
             "2024-03-15 08:30:00-06:00", "2024-03-15 08:31:00-06:00",
             "2024-03-15 08:31:05-06:00"),
            ("Watch", "10", "count", 23.0,
             "2024-03-15 08:31:00-06:00", "2024-03-15 08:32:00-06:00",
             "2024-03-15 08:32:05-06:00"),
        ]
        flush_batch(db, "step_counts", rows)
        result = db.sql("SELECT COUNT(*) FROM step_counts").fetchone()
        assert result is not None
        assert result[0] == 2

    def test_flush_sleep_sessions(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        rows: list[tuple[object, ...]] = [
            ("Watch", "10", "deep",
             "2024-03-14 23:30:00-06:00", "2024-03-15 00:15:00-06:00",
             "2024-03-15 06:00:00-06:00"),
        ]
        flush_batch(db, "sleep_sessions", rows)
        result = db.sql("SELECT stage FROM sleep_sessions").fetchone()
        assert result is not None
        assert result[0] == "deep"

    def test_flush_workouts(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        rows: list[tuple[object, ...]] = [
            ("running", "Watch", "10", 30.5, 5200.0, 320.0,
             "2024-03-15 09:00:00-06:00", "2024-03-15 09:30:30-06:00",
             "2024-03-15 09:31:00-06:00"),
        ]
        flush_batch(db, "workouts", rows)
        result = db.sql("SELECT workout_type, duration FROM workouts").fetchone()
        assert result is not None
        assert result[0] == "running"
        assert result[1] == 30.5

    def test_flush_empty_batch_is_noop(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        flush_batch(db, "step_counts", [])
        result = db.sql("SELECT COUNT(*) FROM step_counts").fetchone()
        assert result is not None
        assert result[0] == 0

    def test_timestamps_parsed_correctly(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        rows: list[tuple[object, ...]] = [
            ("Watch", "10", "count", 45.0,
             "2024-03-15 08:30:00-06:00", "2024-03-15 08:31:00-06:00",
             "2024-03-15 08:31:05-06:00"),
        ]
        flush_batch(db, "step_counts", rows)
        result = db.sql(
            "SELECT start_date::VARCHAR FROM step_counts"
        ).fetchone()
        assert result is not None
        assert "2024-03-15" in result[0]


class TestParseExport:
    def test_parses_sample_export(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        xml_path = FIXTURE_DIR / "sample_export.xml"
        stats, _dob = parse_export(db, xml_path)
        # 2 step records
        assert db.sql("SELECT COUNT(*) FROM step_counts").fetchone()[0] == 2
        # 1 heart rate record
        assert db.sql("SELECT COUNT(*) FROM heart_rate_samples").fetchone()[0] == 1
        # 1 HRV record
        assert db.sql("SELECT COUNT(*) FROM hrv_samples").fetchone()[0] == 1
        # 1 VO2 Max record
        assert db.sql("SELECT COUNT(*) FROM vo2_max").fetchone()[0] == 1
        # 2 sleep records
        assert db.sql("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0] == 2
        # 1 body measurement
        assert db.sql("SELECT COUNT(*) FROM body_measurements").fetchone()[0] == 1
        # 1 walking metric
        assert db.sql("SELECT COUNT(*) FROM walking_metrics").fetchone()[0] == 1
        # 1 respiratory rate
        assert db.sql("SELECT COUNT(*) FROM respiratory_rate").fetchone()[0] == 1
        # 1 oxygen saturation
        assert db.sql("SELECT COUNT(*) FROM oxygen_saturation").fetchone()[0] == 1
        # 1 active energy
        assert db.sql("SELECT COUNT(*) FROM active_energy").fetchone()[0] == 1
        # 1 workout
        assert db.sql("SELECT COUNT(*) FROM workouts").fetchone()[0] == 1
        # 1 activity summary
        assert db.sql("SELECT COUNT(*) FROM activity_summary").fetchone()[0] == 1
        # Unknown type (blood pressure) skipped
        assert stats["skipped"] >= 1

    def test_type_filter(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        xml_path = FIXTURE_DIR / "sample_export.xml"
        parse_export(db, xml_path, type_filter={"step_counts"})
        assert db.sql("SELECT COUNT(*) FROM step_counts").fetchone()[0] == 2
        assert db.sql("SELECT COUNT(*) FROM heart_rate_samples").fetchone()[0] == 0

    def test_since_filter(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        xml_path = FIXTURE_DIR / "sample_export.xml"
        # Filter to after 2024-03-15: deep sleep (2024-03-14 23:30) excluded,
        # REM sleep (2024-03-15 00:15) included
        parse_export(db, xml_path, since="2024-03-15")
        sleep_count = db.sql("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0]
        assert sleep_count == 1
        stage = db.sql("SELECT stage FROM sleep_sessions").fetchone()[0]
        assert stage == "rem"

    def test_returns_stats(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        xml_path = FIXTURE_DIR / "sample_export.xml"
        stats, _dob = parse_export(db, xml_path)
        assert "step_counts" in stats
        assert stats["step_counts"] == 2
        assert "total" in stats


class TestExtractDateOfBirth:
    def test_parses_dob_from_me_element(self, db: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        create_tables(db)
        xml = tmp_path / "dob_test.xml"
        xml.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<HealthData>\n"
            ' <Me HKCharacteristicTypeIdentifierDateOfBirth="1990-05-15"/>\n'
            "</HealthData>"
        )
        stats, dob = parse_export(db, xml)
        assert dob == "1990-05-15"

    def test_missing_dob_returns_none(self, db: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        create_tables(db)
        xml = tmp_path / "no_dob_test.xml"
        xml.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<HealthData>\n"
            ' <Me HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale"/>\n'
            "</HealthData>"
        )
        stats, dob = parse_export(db, xml)
        assert dob is None


class TestComputeHrZones:
    def test_classifies_samples_into_zones(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        # Insert a workout from 09:00 to 09:30
        db.sql("""
            INSERT INTO workouts VALUES
            ('running', 'Watch', '10', 30.0, 5000.0, 300.0,
             '2024-03-15 09:00:00-06', '2024-03-15 09:30:00-06', NULL)
        """)
        # Insert HR samples during the workout
        # Max HR = 200 -> Z1 <120, Z2 120-140, Z3 140-160, Z4 160-180, Z5 180+
        db.sql("""
            INSERT INTO heart_rate_samples VALUES
            ('Watch', '10', 'count/min', 110, '2024-03-15 09:00:00-06', '2024-03-15 09:05:00-06', NULL),
            ('Watch', '10', 'count/min', 130, '2024-03-15 09:05:00-06', '2024-03-15 09:15:00-06', NULL),
            ('Watch', '10', 'count/min', 155, '2024-03-15 09:15:00-06', '2024-03-15 09:25:00-06', NULL),
            ('Watch', '10', 'count/min', 175, '2024-03-15 09:25:00-06', '2024-03-15 09:30:00-06', NULL)
        """)
        compute_hr_zones(db, max_hr=200)
        rows = db.sql("""
            SELECT zone, seconds FROM workout_hr_zones
            ORDER BY zone
        """).fetchall()
        zones = {zone: secs for zone, secs in rows}
        assert zones[1] == 300.0   # 5 min = 300s (HR 110, Z1)
        assert zones[2] == 600.0   # 10 min = 600s (HR 130, Z2)
        assert zones[3] == 600.0   # 10 min = 600s (HR 155, Z3)
        assert zones[4] == 300.0   # 5 min = 300s (HR 175, Z4)

    def test_no_overlapping_samples_produces_no_rows(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO workouts VALUES
            ('running', 'Watch', '10', 30.0, NULL, NULL,
             '2024-03-15 09:00:00-06', '2024-03-15 09:30:00-06', NULL)
        """)
        # HR sample is outside workout window
        db.sql("""
            INSERT INTO heart_rate_samples VALUES
            ('Watch', '10', 'count/min', 72, '2024-03-15 08:00:00-06', '2024-03-15 08:00:00-06', NULL)
        """)
        compute_hr_zones(db, max_hr=200)
        count = db.sql("SELECT COUNT(*) FROM workout_hr_zones").fetchone()[0]
        assert count == 0

    def test_uses_estimated_max_hr_when_none(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO workouts VALUES
            ('running', 'Watch', '10', 30.0, NULL, NULL,
             '2024-03-15 09:00:00-06', '2024-03-15 09:30:00-06', NULL)
        """)
        # HR of 130 with max_hr=None and dob="1990-05-15"
        # Age at 2024-03-15 = 33, Tanaka: 208 - 0.7*33 = 184.9 -> 184
        # Z2 = 60-70% of 184 = 110.4-128.8 -> HR 130 is Z3
        db.sql("""
            INSERT INTO heart_rate_samples VALUES
            ('Watch', '10', 'count/min', 130, '2024-03-15 09:00:00-06', '2024-03-15 09:10:00-06', NULL)
        """)
        compute_hr_zones(db, max_hr=None, date_of_birth="1990-05-15")
        zone = db.sql("SELECT zone FROM workout_hr_zones").fetchone()[0]
        assert zone == 3  # 130 / 184 = 70.6% -> Z3

    def test_raises_without_max_hr_or_dob(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO workouts VALUES
            ('running', 'Watch', '10', 30.0, NULL, NULL,
             '2024-03-15 09:00:00-06', '2024-03-15 09:30:00-06', NULL)
        """)
        db.sql("""
            INSERT INTO heart_rate_samples VALUES
            ('Watch', '10', 'count/min', 130, '2024-03-15 09:00:00-06', '2024-03-15 09:10:00-06', NULL)
        """)
        # No max_hr and no DOB -- should skip zone computation and print warning
        compute_hr_zones(db, max_hr=None, date_of_birth=None)
        count = db.sql("SELECT COUNT(*) FROM workout_hr_zones").fetchone()[0]
        assert count == 0
