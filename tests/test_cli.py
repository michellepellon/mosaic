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
