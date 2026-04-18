"""Tests for the CLI module."""

import zipfile
from pathlib import Path

import duckdb
import pytest

from mosaic.cli import main, resolve_xml_path

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestResolveXmlPath:
    def test_xml_file_returned_directly(self) -> None:
        xml_path = FIXTURE_DIR / "sample_export.xml"
        result, cleanup = resolve_xml_path(xml_path)
        assert result == xml_path
        assert cleanup is None

    def test_zip_file_extracts_export_xml(self, tmp_path: Path) -> None:
        # Create a test zip containing the sample export
        zip_path = tmp_path / "export.zip"
        xml_source = FIXTURE_DIR / "sample_export.xml"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(xml_source, "apple_health_export/export.xml")

        result, cleanup = resolve_xml_path(zip_path)
        assert result.name == "export.xml"
        assert result.exists()
        if cleanup:
            cleanup()

    def test_missing_file_raises(self) -> None:
        with pytest.raises(SystemExit):
            resolve_xml_path(Path("/nonexistent/export.xml"))

    def test_zip_without_export_xml_raises(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("other.txt", "not health data")
        with pytest.raises(SystemExit):
            resolve_xml_path(zip_path)


class TestMainEndToEnd:
    def test_basic_import(self, tmp_path: Path) -> None:
        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        main([str(xml_path), "--output", str(db_path)])
        conn = duckdb.connect(str(db_path), read_only=True)
        assert conn.sql("SELECT COUNT(*) FROM step_counts").fetchone()[0] == 2
        assert conn.sql("SELECT COUNT(*) FROM workouts").fetchone()[0] == 1
        # Views should be queryable
        conn.sql("SELECT * FROM daily_steps")
        conn.close()

    def test_force_flag_truncates(self, tmp_path: Path) -> None:
        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        main([str(xml_path), "--output", str(db_path)])
        main([str(xml_path), "--output", str(db_path), "--force"])
        conn = duckdb.connect(str(db_path), read_only=True)
        # Should have same count (not doubled)
        assert conn.sql("SELECT COUNT(*) FROM step_counts").fetchone()[0] == 2
        conn.close()

    def test_types_filter(self, tmp_path: Path) -> None:
        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        main([str(xml_path), "--output", str(db_path), "--types", "step_counts"])
        conn = duckdb.connect(str(db_path), read_only=True)
        assert conn.sql("SELECT COUNT(*) FROM step_counts").fetchone()[0] == 2
        assert conn.sql("SELECT COUNT(*) FROM heart_rate_samples").fetchone()[0] == 0
        conn.close()

    def test_labs_import(self, tmp_path: Path) -> None:
        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        labs_csv = tmp_path / "labs.csv"
        labs_csv.write_text(
            "date,test,value,unit,ref_low,ref_high,longevity_target,optimal\n"
            "2024-01-30,Glucose,79,mg/dL,70,99,<90,72-85\n"
            "2024-01-30,ALT,25,U/L,0,50,<30,<20\n"
        )
        main([str(xml_path), "--output", str(db_path), "--labs", str(labs_csv)])
        conn = duckdb.connect(str(db_path), read_only=True)
        assert conn.sql("SELECT COUNT(*) FROM clinical_labs").fetchone()[0] == 2
        # Dashboard labs view should also work
        rows = conn.sql("SELECT * FROM dashboard_labs").fetchall()
        assert len(rows) == 2
        conn.close()

    def test_labs_missing_file_raises(self, tmp_path: Path) -> None:
        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        with pytest.raises(SystemExit):
            main([str(xml_path), "--output", str(db_path), "--labs", "/nonexistent/labs.csv"])

    def test_json_export(self, tmp_path: Path) -> None:
        import json

        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        json_path = tmp_path / "out.json"
        main([
            str(xml_path),
            "--output", str(db_path),
            "--json", str(json_path),
        ])
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert "scorecard" in data
        assert "steps" in data
        assert "labs" in data
        assert len(data["steps"]) == 1  # 2 raw step records aggregate to 1 daily row

    def test_json_export_with_labs(self, tmp_path: Path) -> None:
        import json

        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        json_path = tmp_path / "out.json"
        labs_csv = tmp_path / "labs.csv"
        labs_csv.write_text(
            "date,test,value,unit,ref_low,ref_high,longevity_target,optimal\n"
            "2024-01-30,Glucose,79,mg/dL,70,99,<90,72-85\n"
        )
        main([
            str(xml_path),
            "--output", str(db_path),
            "--labs", str(labs_csv),
            "--json", str(json_path),
        ])
        data = json.loads(json_path.read_text())
        assert isinstance(data["labs"], dict)
        assert "groups" in data["labs"]


class TestMaxHrFlag:
    def test_max_hr_computes_zones(self, tmp_path: Path) -> None:
        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        main([str(xml_path), "--output", str(db_path), "--max-hr", "185"])
        conn = duckdb.connect(str(db_path), read_only=True)
        count = conn.sql("SELECT COUNT(*) FROM workout_hr_zones").fetchone()[0]
        # Fixture has a workout 09:00-09:30 and HR samples overlapping it
        assert count > 0
        conn.close()

    def test_no_max_hr_uses_dob_from_export(self, tmp_path: Path) -> None:
        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        # Fixture's <Me> element has DOB, so zones should still be computed
        main([str(xml_path), "--output", str(db_path)])
        conn = duckdb.connect(str(db_path), read_only=True)
        count = conn.sql("SELECT COUNT(*) FROM workout_hr_zones").fetchone()[0]
        assert count > 0
        conn.close()


class TestHrZoneIntegration:
    def test_zones_match_expected_classification(self, tmp_path: Path) -> None:
        """Verify fixture HR samples are classified correctly.

        Fixture workout: 09:00-09:30, DOB: 1990-05-15 -> age ~33-36 -> max HR ~182-184
        Z2 = 60-70% of ~183 = ~110-128
        Z3 = 70-80% of ~183 = ~128-146
        Z4 = 80-90% of ~183 = ~146-165
        HR 125 (09:00-09:10) -> Z2 (10 min)
        HR 145 (09:10-09:20) -> Z3 (10 min)
        HR 162 (09:20-09:30) -> Z4 (10 min)
        """
        xml_path = FIXTURE_DIR / "sample_export.xml"
        db_path = tmp_path / "test.duckdb"
        main([str(xml_path), "--output", str(db_path)])
        conn = duckdb.connect(str(db_path), read_only=True)
        zones = dict(conn.sql(
            "SELECT zone, seconds FROM workout_hr_zones ORDER BY zone"
        ).fetchall())
        assert zones[2] == 600.0  # 10 min in Z2
        assert zones[3] == 600.0  # 10 min in Z3
        assert zones[4] == 600.0  # 10 min in Z4
        # Dashboard view should also work
        rows = conn.sql("SELECT z2, z4, total FROM dashboard_hrzones").fetchall()
        assert len(rows) == 1
        z2, z4, total = rows[0]
        assert z2 == 10.0     # 10 min
        assert z4 == 10.0     # 10 min (Z4 only, no Z5)
        assert total == 30.0  # all 3 zones
        conn.close()
