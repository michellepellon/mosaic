"""Tests for the JSON export module."""

import json
from pathlib import Path

import duckdb

from mosaic.export import export_json
from mosaic.schema import create_tables, create_views


class TestExportJson:
    def test_writes_json_file(self, db: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        create_tables(db)
        create_views(db)
        out = tmp_path / "test.json"
        export_json(db, out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_contains_all_required_keys(
        self, db: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        create_tables(db)
        create_views(db)
        out = tmp_path / "test.json"
        export_json(db, out)
        data = json.loads(out.read_text())
        expected_keys = {
            "scorecard", "steps", "sleep", "rhr", "hrv", "spo2", "vo2",
            "bodyfat", "weight", "exercise", "hrzones", "labs",
            "walking_speed", "walking_asymmetry", "respiratory_rate",
        }
        assert expected_keys == set(data.keys())

    def test_labs_is_pretransformed(
        self, db: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO clinical_labs VALUES
            ('2024-01-30', 'Glucose', 79.0, 'mg/dL', 70, 99, '<90', '72-85')
        """)
        create_views(db)
        out = tmp_path / "test.json"
        export_json(db, out)
        data = json.loads(out.read_text())
        labs = data["labs"]
        assert isinstance(labs, dict)
        assert "date" in labs
        assert "groups" in labs
        assert isinstance(labs["groups"], dict)

    def test_labs_status_computed(
        self, db: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO clinical_labs VALUES
            ('2024-01-30', 'Glucose', 79.0, 'mg/dL', 70, 99, '<90', '72-85')
        """)
        create_views(db)
        out = tmp_path / "test.json"
        export_json(db, out)
        data = json.loads(out.read_text())
        tests = data["labs"]["groups"]["Metabolic Panel"]
        assert len(tests) == 1
        assert tests[0]["status"] == "green"

    def test_array_data_has_date_key(
        self, db: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        create_tables(db)
        for i in range(3):
            db.sql(f"""
                INSERT INTO step_counts VALUES
                ('Watch', '10', 'count', {1000 + i * 100},
                 '2024-01-0{i+1} 08:00:00-06', '2024-01-0{i+1} 08:01:00-06',
                 '2024-01-0{i+1} 08:01:00-06')
            """)
        create_views(db)
        out = tmp_path / "test.json"
        export_json(db, out)
        data = json.loads(out.read_text())
        assert len(data["steps"]) == 3
        assert "d" in data["steps"][0]

    def test_empty_labs_returns_empty_groups(
        self, db: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        create_tables(db)
        create_views(db)
        out = tmp_path / "test.json"
        export_json(db, out)
        data = json.loads(out.read_text())
        assert data["labs"] == {"date": "", "source": "", "groups": {}}
