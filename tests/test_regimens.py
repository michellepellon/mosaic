"""Tests for regimens and regimen_events schema."""

import duckdb

from mosaic.schema import TABLE_NAMES, create_tables, create_views


def _columns(conn: duckdb.DuckDBPyConnection, table: str) -> dict[str, str]:
    rows = conn.sql(
        f"SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_name = '{table}'"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def test_regimens_in_table_names():
    assert "regimens" in TABLE_NAMES
    assert "regimen_events" in TABLE_NAMES


def test_regimens_columns(db: duckdb.DuckDBPyConnection):
    create_tables(db)
    cols = _columns(db, "regimens")
    assert cols["id"] == "INTEGER"
    assert cols["name"] == "VARCHAR"
    assert cols["brand"] == "VARCHAR"
    assert cols["category"] == "VARCHAR"
    assert cols["dose_amount"] == "DOUBLE"
    assert cols["dose_unit"] == "VARCHAR"
    assert cols["schedule"] == "VARCHAR"
    assert cols["start_date"] == "DATE"
    assert cols["end_date"] == "DATE"
    assert cols["notes"] == "VARCHAR"


def test_regimen_events_columns(db: duckdb.DuckDBPyConnection):
    create_tables(db)
    cols = _columns(db, "regimen_events")
    for c in ("id", "regimen_id", "event_date", "event_type", "slot",
             "substance", "brand", "dose_amount", "dose_unit", "notes"):
        assert c in cols, f"missing column {c}"
    assert cols["event_date"] == "DATE"
    assert cols["dose_amount"] == "DOUBLE"


def test_regimens_insert_round_trip(db: duckdb.DuckDBPyConnection):
    create_tables(db)
    db.execute(
        "INSERT INTO regimens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [1, "Creatine", "Thorne", "supplement", 5.0, "g",
         "morning", "2025-09-12", None, ""],
    )
    row = db.sql("SELECT name, dose_amount FROM regimens WHERE id = 1").fetchone()
    assert row == ("Creatine", 5.0)


def test_regimen_event_round_trip(db: duckdb.DuckDBPyConnection):
    create_tables(db)
    db.execute(
        "INSERT INTO regimens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [1, "Magnesium", "Thorne", "supplement", 400.0, "mg",
         "both", "2026-01-15", None, ""],
    )
    db.execute(
        "INSERT INTO regimen_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [1, 1, "2026-04-28", "miss", "morning", None, None, None, None, ""],
    )
    row = db.sql(
        "SELECT regimen_id, event_type, slot FROM regimen_events WHERE id = 1"
    ).fetchone()
    assert row == (1, "miss", "morning")


def _seed_regimens(conn: duckdb.DuckDBPyConnection) -> None:
    create_tables(conn)
    conn.execute(
        "INSERT INTO regimens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [1, "Creatine", "Thorne", "supplement", 5.0, "g",
         "morning", "2025-09-12", None, ""],
    )
    conn.execute(
        "INSERT INTO regimens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [2, "Magnesium", "Thorne", "supplement", 400.0, "mg",
         "both", "2026-01-15", None, ""],
    )
    conn.execute(
        "INSERT INTO regimens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [3, "Old Vitamin", None, "supplement", 1000.0, "IU",
         "morning", "2024-01-01", "2025-06-30", ""],
    )
    conn.execute(
        "INSERT INTO regimens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [4, "THC/CBD gummy", "Wyld", "cannabis", 10.0, "mg",
         "as_needed", "2026-02-01", None, "1:1"],
    )


def test_active_stack_excludes_ended(db: duckdb.DuckDBPyConnection):
    _seed_regimens(db)
    create_views(db)
    rows = db.sql(
        "SELECT id FROM dashboard_active_stack ORDER BY id"
    ).fetchall()
    ids = {r[0] for r in rows}
    assert ids == {1, 2, 4}  # 3 is ended


def test_stack_history_includes_all(db: duckdb.DuckDBPyConnection):
    _seed_regimens(db)
    create_views(db)
    rows = db.sql(
        "SELECT id, is_active FROM dashboard_stack_history ORDER BY id"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        (1, True), (2, True), (3, False), (4, True),
    ]


def test_stack_adherence_counts_misses(db: duckdb.DuckDBPyConnection):
    _seed_regimens(db)
    db.execute(
        "INSERT INTO regimen_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [1, 2, "2026-04-27", "miss", "morning", None, None, None, None, ""],
    )
    db.execute(
        "INSERT INTO regimen_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [2, 2, "2026-04-27", "miss", "evening", None, None, None, None, ""],
    )
    # taken events should NOT count toward miss_count
    db.execute(
        "INSERT INTO regimen_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [3, 4, "2026-04-27", "taken", "as_needed", None, None, None, None, ""],
    )
    create_views(db)
    rows = db.sql(
        "SELECT slot, miss_count FROM dashboard_stack_adherence "
        "WHERE event_date = '2026-04-27' ORDER BY slot"
    ).fetchall()
    assert sorted(rows) == [("evening", 1), ("morning", 1)]
