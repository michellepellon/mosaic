"""Tests for the readiness scoring module."""
# ABOUTME: Tests readiness score computation, factor scoring, prescriptions,
# ABOUTME: and watch list alert generation.

import duckdb

from mosaic.readiness import _factor_score, _target_score, compute_readiness
from mosaic.schema import create_tables, create_views


class TestFactorScore:
    def test_at_baseline_returns_75(self) -> None:
        assert _factor_score(50.0, 50.0) == 75.0

    def test_above_baseline_returns_higher(self) -> None:
        assert _factor_score(55.0, 50.0) == 100.0  # 10% above

    def test_below_baseline_returns_lower(self) -> None:
        assert _factor_score(45.0, 50.0) == 50.0  # 10% below

    def test_well_below_baseline(self) -> None:
        assert _factor_score(40.0, 50.0) == 25.0  # 20% below

    def test_inverted_for_rhr(self) -> None:
        # RHR: being below baseline is good
        assert _factor_score(55.0, 60.0, invert=True) > 75.0
        assert _factor_score(65.0, 60.0, invert=True) < 75.0

    def test_none_returns_neutral(self) -> None:
        assert _factor_score(None, 50.0) == 75.0
        assert _factor_score(50.0, None) == 75.0


class TestTargetScore:
    def test_at_target_returns_100(self) -> None:
        assert _target_score(7.5, target=7.5, floor=5.0) == 100.0

    def test_above_target(self) -> None:
        assert _target_score(8.0, target=7.5, floor=5.0) == 100.0

    def test_at_floor(self) -> None:
        assert _target_score(5.0, target=7.5, floor=5.0) == 25.0

    def test_midpoint(self) -> None:
        score = _target_score(6.25, target=7.5, floor=5.0)
        assert 40 < score < 70  # roughly middle

    def test_none_returns_neutral(self) -> None:
        assert _target_score(None, target=7.5, floor=5.0) == 75.0


class TestComputeReadiness:
    def test_returns_all_fields(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        result = compute_readiness(db)
        assert "score" in result
        assert "status" in result
        assert "prescription" in result
        assert "factors" in result
        assert "alerts" in result

    def test_empty_data_returns_neutral(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        result = compute_readiness(db)
        assert result["score"] == 75.0  # all neutral
        assert result["status"] == "ready"

    def test_peak_status(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        # Insert excellent data: high HRV, low RHR, good sleep
        for i in range(35):
            day = f"2024-03-{i + 1:02d}" if i < 31 else f"2024-04-{i - 30:02d}"
            db.sql(f"""
                INSERT INTO hrv_samples VALUES
                ('Watch', '10', 'ms', {40 + i * 0.1},
                 '{day} 08:00:00-06', '{day} 08:00:00-06', NULL)
            """)
            db.sql(f"""
                INSERT INTO resting_heart_rate VALUES
                ('Watch', '10', 'count/min', {58 - i * 0.05},
                 '{day} 08:00:00-06', '{day} 08:00:00-06', NULL)
            """)
        # Good sleep last night
        db.sql("""
            INSERT INTO sleep_sessions VALUES
            ('Watch', '10', 'deep', '2024-04-04 23:00:00-06', '2024-04-05 01:00:00-06', NULL),
            ('Watch', '10', 'rem', '2024-04-05 01:00:00-06', '2024-04-05 03:00:00-06', NULL),
            ('Watch', '10', 'core', '2024-04-05 03:00:00-06', '2024-04-05 06:30:00-06', NULL)
        """)
        # Good SpO2
        db.sql("""
            INSERT INTO oxygen_saturation VALUES
            ('Watch', '10', '%', 0.95, '2024-04-05 02:00:00-06', '2024-04-05 02:00:00-06', NULL)
        """)
        create_views(db)
        result = compute_readiness(db)
        assert result["score"] >= 70
        assert result["status"] in ("peak", "ready")

    def test_alerts_list_type(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        result = compute_readiness(db)
        assert isinstance(result["alerts"], list)
