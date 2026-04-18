"""Tests for the FHIR clinical records parser."""

import json
from pathlib import Path

import duckdb

from mosaic.fhir import parse_clinical_records
from mosaic.schema import create_tables

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_clinical_records"


class TestParseClinicalRecords:
    def test_parses_diagnostic_report(
        self, db: duckdb.DuckDBPyConnection,
    ) -> None:
        create_tables(db)
        count = parse_clinical_records(db, FIXTURE_DIR)
        # DiagnosticReport has 2 labs, Observation has 1
        assert count == 3

    def test_inserts_correct_values(
        self, db: duckdb.DuckDBPyConnection,
    ) -> None:
        create_tables(db)
        parse_clinical_records(db, FIXTURE_DIR)
        row = db.sql("""
            SELECT draw_date, test, loinc_code, value, unit
            FROM clinical_labs
            WHERE loinc_code = '2345-7'
            ORDER BY draw_date
        """).fetchall()
        assert len(row) == 2
        # First draw: Jan 30 from DiagnosticReport
        assert str(row[0][0]) == "2024-01-30"
        assert row[0][1] == "Glucose"
        assert row[0][3] == 85.0
        # Second draw: Jul 15 from standalone Observation
        assert str(row[1][0]) == "2024-07-15"
        assert row[1][3] == 92.0

    def test_inserts_reference_range(
        self, db: duckdb.DuckDBPyConnection,
    ) -> None:
        create_tables(db)
        parse_clinical_records(db, FIXTURE_DIR)
        row = db.sql("""
            SELECT ref_low, ref_high FROM clinical_labs
            WHERE loinc_code = '2345-7' LIMIT 1
        """).fetchone()
        assert row is not None
        assert row[0] == 70.0
        assert row[1] == 99.0

    def test_deduplicates_on_reimport(
        self, db: duckdb.DuckDBPyConnection,
    ) -> None:
        create_tables(db)
        parse_clinical_records(db, FIXTURE_DIR)
        parse_clinical_records(db, FIXTURE_DIR)
        count = db.sql(
            "SELECT COUNT(*) FROM clinical_labs"
        ).fetchone()[0]
        assert count == 3  # Not 6

    def test_empty_directory(
        self, db: duckdb.DuckDBPyConnection, tmp_path: Path,
    ) -> None:
        create_tables(db)
        empty = tmp_path / "empty_records"
        empty.mkdir()
        count = parse_clinical_records(db, empty)
        assert count == 0

    def test_skips_non_lab_observations(
        self, db: duckdb.DuckDBPyConnection, tmp_path: Path,
    ) -> None:
        create_tables(db)
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        vital = {
            "resourceType": "Observation",
            "category": [{"coding": [{"code": "vital-signs"}]}],
            "effectiveDateTime": "2024-01-30T08:00:00Z",
            "code": {"coding": [
                {"system": "http://loinc.org", "display": "Pulse",
                 "code": "8867-4"}
            ]},
            "valueQuantity": {"value": 72, "unit": "bpm"},
            "status": "final",
        }
        (records_dir / "Observation-vital.json").write_text(
            json.dumps(vital)
        )
        count = parse_clinical_records(db, records_dir)
        assert count == 0

    def test_skips_string_valued_observations(
        self, db: duckdb.DuckDBPyConnection, tmp_path: Path,
    ) -> None:
        create_tables(db)
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        string_obs = {
            "resourceType": "Observation",
            "category": [{"coding": [{"code": "laboratory"}]}],
            "effectiveDateTime": "2024-01-30T08:00:00Z",
            "code": {"coding": [
                {"system": "http://loinc.org",
                 "display": "COVID-19", "code": "94500-6"}
            ]},
            "valueString": "Not-Detected",
            "status": "final",
        }
        (records_dir / "Observation-string.json").write_text(
            json.dumps(string_obs)
        )
        count = parse_clinical_records(db, records_dir)
        assert count == 0
