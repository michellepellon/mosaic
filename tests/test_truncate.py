"""Tests for truncate_tables splitting health vs user data."""

import duckdb

from mosaic.schema import (
    HEALTH_DATA_TABLES,
    TABLE_NAMES,
    USER_DATA_TABLES,
    create_tables,
    truncate_tables,
)


def test_partition():
    assert USER_DATA_TABLES & HEALTH_DATA_TABLES == set()
    assert USER_DATA_TABLES | HEALTH_DATA_TABLES == TABLE_NAMES


def test_user_data_tables_membership():
    assert USER_DATA_TABLES == frozenset({
        "athlete_profile", "training_blocks", "goals",
        "regimens", "regimen_events",
    })


def test_truncate_preserves_user_data(db: duckdb.DuckDBPyConnection):
    create_tables(db)
    db.execute(
        "INSERT INTO athlete_profile VALUES (?, ?)", ["name", "Michelle"]
    )
    db.execute(
        "INSERT INTO goals VALUES (?, ?, ?, ?, ?, ?)",
        [1, "Marathon", "2026-09-01", "race_time", 220.0, ""],
    )
    db.execute(
        "INSERT INTO regimens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [1, "Creatine", "Thorne", "supplement", 5.0, "g",
         "morning", "2025-09-12", None, ""],
    )
    db.execute(
        "INSERT INTO training_blocks VALUES (?, ?, ?, ?, ?, ?, ?)",
        [1, "Base", "base", "2026-04-01", "2026-04-30", 180, ""],
    )
    db.execute(
        "INSERT INTO step_counts VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["Watch", "1.0", "count", 1234.0,
         "2026-04-27 08:00:00-06:00", "2026-04-27 08:01:00-06:00", None],
    )

    truncate_tables(db)

    step_count_result = db.sql("SELECT COUNT(*) FROM step_counts").fetchone()
    assert step_count_result is not None
    assert step_count_result[0] == 0

    profile_result = db.sql("SELECT COUNT(*) FROM athlete_profile").fetchone()
    assert profile_result is not None
    assert profile_result[0] == 1

    goals_result = db.sql("SELECT COUNT(*) FROM goals").fetchone()
    assert goals_result is not None
    assert goals_result[0] == 1

    regimens_result = db.sql("SELECT COUNT(*) FROM regimens").fetchone()
    assert regimens_result is not None
    assert regimens_result[0] == 1

    training_blocks_result = db.sql("SELECT COUNT(*) FROM training_blocks").fetchone()
    assert training_blocks_result is not None
    assert training_blocks_result[0] == 1
