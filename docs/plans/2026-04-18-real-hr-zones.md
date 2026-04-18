# Real HR Zones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fabricated HR zone estimates with real zone computation from heart rate samples recorded during workouts.

**Architecture:** Post-processing pass after XML ingestion queries `heart_rate_samples` overlapping each workout's time window, classifies samples into zones based on max HR (user-provided via `--max-hr` or estimated from DOB via Tanaka formula), and stores time-in-zone in a new `workout_hr_zones` table. A replaced `dashboard_hrzones` view aggregates to weekly totals. Zone computation uses a single DuckDB SQL query with window functions -- no Python row-by-row iteration.

**Tech Stack:** Python 3.14, DuckDB, PyArrow, pytest

**File Map:**
| File | Action | Responsibility |
|------|--------|----------------|
| `src/mosaic/schema.py` | Modify | Add `workout_hr_zones` DDL, update `TABLE_NAMES`, replace `dashboard_hrzones` view |
| `src/mosaic/parser.py` | Modify | Extract DOB from `<Me>` element, add `compute_hr_zones()` function |
| `src/mosaic/cli.py` | Modify | Add `--max-hr` flag, call `compute_hr_zones()` in pipeline |
| `src/mosaic/export.py` | Modify | Update hrzones query to include `total` column |
| `dashboard.html` | Modify | Update hrzones DuckDB-WASM query and `other` segment computation |
| `tests/test_schema.py` | Modify | Tests for new table and replaced view |
| `tests/test_parser.py` | Modify | Tests for DOB extraction and zone computation |
| `tests/test_cli.py` | Modify | Update call sites for new `parse_export` return type, end-to-end test |
| `tests/test_export.py` | Modify | Add test for hrzones `total` column in JSON export |
| `tests/fixtures/sample_export.xml` | Modify | Add DOB to `<Me>`, add HR samples during workout window |

---

### Task 1: Add `workout_hr_zones` table to schema

**Files:**
- Modify: `src/mosaic/schema.py:48-65` (TABLE_NAMES), `src/mosaic/schema.py:84-155` (_TABLE_DDL)
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_schema.py`:

```python
class TestWorkoutHrZonesTable:
    def test_creates_workout_hr_zones_table(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        result = db.sql("SELECT * FROM workout_hr_zones LIMIT 0").description
        col_names = [col[0] for col in result]
        assert "workout_start" in col_names
        assert "workout_type" in col_names
        assert "zone" in col_names
        assert "seconds" in col_names
        assert "source_name" in col_names

    def test_workout_hr_zones_in_table_names(self) -> None:
        assert "workout_hr_zones" in TABLE_NAMES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py::TestWorkoutHrZonesTable -v`
Expected: FAIL with `Catalog Error: Table with name workout_hr_zones does not exist`

- [ ] **Step 3: Add table DDL and update TABLE_NAMES**

In `src/mosaic/schema.py`, add `"workout_hr_zones"` to the `TABLE_NAMES` frozenset (after `"workouts"`):

```python
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
    "workout_hr_zones",
    "activity_summary",
    "clinical_labs",
})
```

Add the DDL to `_TABLE_DDL` (after the `"workouts"` entry):

```python
    "workout_hr_zones": """CREATE TABLE IF NOT EXISTS workout_hr_zones (
        workout_start   TIMESTAMPTZ NOT NULL,
        workout_type    VARCHAR NOT NULL,
        zone            INTEGER NOT NULL,
        seconds         DOUBLE NOT NULL,
        source_name     VARCHAR NOT NULL
    )""",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py::TestWorkoutHrZonesTable -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/mosaic/schema.py tests/test_schema.py
git commit -m "feat(schema): add workout_hr_zones table"
```

---

### Task 2: Replace `dashboard_hrzones` view

**Files:**
- Modify: `src/mosaic/schema.py:291-295` (dashboard_hrzones view in `_VIEW_SQL`)
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_schema.py`:

```python
class TestDashboardHrzonesView:
    def test_columns_include_total(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        create_views(db)
        cols = [c[0] for c in db.sql("SELECT * FROM dashboard_hrzones LIMIT 0").description]
        assert set(cols) == {"date", "z2", "z4", "total"}

    def test_aggregates_zones_correctly(self, db: duckdb.DuckDBPyConnection) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO workout_hr_zones VALUES
            ('2024-01-15 09:00:00-06', 'running', 1, 300, 'Watch'),
            ('2024-01-15 09:00:00-06', 'running', 2, 1200, 'Watch'),
            ('2024-01-15 09:00:00-06', 'running', 3, 600, 'Watch'),
            ('2024-01-15 09:00:00-06', 'running', 4, 180, 'Watch'),
            ('2024-01-15 09:00:00-06', 'running', 5, 60, 'Watch')
        """)
        create_views(db)
        rows = db.sql("SELECT * FROM dashboard_hrzones").fetchall()
        assert len(rows) == 1
        date, z2, z4, total = rows[0]
        assert z2 == 1200 / 60.0  # 20 min in Z2
        assert z4 == (180 + 60) / 60.0  # Z4 + Z5 = 4 min
        assert total == (300 + 1200 + 600 + 180 + 60) / 60.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py::TestDashboardHrzonesView -v`
Expected: FAIL -- old view queries `workouts`, not `workout_hr_zones`

- [ ] **Step 3: Replace the view SQL**

In `src/mosaic/schema.py`, find the `dashboard_hrzones` entry in `_VIEW_SQL` and replace it:

Old:
```python
    """CREATE OR REPLACE VIEW dashboard_hrzones AS
    SELECT DATE_TRUNC('week', start_date::TIMESTAMP)::DATE AS date,
        SUM(duration / 60.0 * 0.4) AS z2,
        SUM(duration / 60.0 * 0.1) AS z4
    FROM workouts GROUP BY 1 ORDER BY 1""",
```

New:
```python
    """CREATE OR REPLACE VIEW dashboard_hrzones AS
    SELECT DATE_TRUNC('week', workout_start::TIMESTAMP)::DATE AS date,
        COALESCE(SUM(seconds) FILTER (WHERE zone = 2), 0) / 60.0 AS z2,
        COALESCE(SUM(seconds) FILTER (WHERE zone >= 4), 0) / 60.0 AS z4,
        COALESCE(SUM(seconds), 0) / 60.0 AS total
    FROM workout_hr_zones GROUP BY 1 ORDER BY 1""",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py::TestDashboardHrzonesView -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/mosaic/schema.py tests/test_schema.py
git commit -m "feat(schema): replace fabricated hrzones view with real zone data"
```

---

### Task 3: Extract date of birth from `<Me>` element

**Files:**
- Modify: `src/mosaic/parser.py:274-343` (parse_export)
- Modify: `src/mosaic/cli.py:114-120` (parse_export call site)
- Modify: `tests/test_parser.py` (TestParseExport call sites)
- Modify: `tests/test_cli.py` (indirect, via main)
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_parser.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parser.py::TestExtractDateOfBirth -v`
Expected: FAIL -- `parse_export` returns `dict`, not a tuple

- [ ] **Step 3: Update parse_export to return DOB**

In `src/mosaic/parser.py`, change the `parse_export` function:

1. Update the return type:
```python
def parse_export(
    conn: _duckdb.DuckDBPyConnection,
    xml_path: Path,
    *,
    type_filter: set[str] | None = None,
    since: str | None = None,
    batch_size: int = 50_000,
) -> tuple[dict[str, int], str | None]:
    """Stream-parse an Apple Health export.xml and ingest into DuckDB.

    Returns (stats_dict, date_of_birth). stats_dict maps table_name -> row_count,
    plus 'total', 'skipped', 'errors'. date_of_birth is from the <Me> element or None.
    """
```

2. Add `date_of_birth` variable after `processed = 0`:
```python
    date_of_birth: str | None = None
```

3. Add `Me` handling in the main loop, after the `elif tag == "ActivitySummary":` block and before the `else:` block:
```python
        elif tag == "Me":
            dob = elem.attrib.get("HKCharacteristicTypeIdentifierDateOfBirth")
            if dob:
                date_of_birth = dob
            elem.clear()
            continue
```

4. Update the return statement at the end of `parse_export`:
```python
    stats["total"] = sum(v for k, v in stats.items() if k not in ("skipped", "errors", "total"))
    return dict(stats), date_of_birth
```

- [ ] **Step 4: Update all call sites**

In `src/mosaic/cli.py`, update line 114:
```python
        stats, date_of_birth = parse_export(
            conn,
            xml_path,
            type_filter=type_filter,
            since=args.since,
            batch_size=args.batch_size,
        )
```

In `tests/test_parser.py`, update all `TestParseExport` methods to unpack tuples:

In `test_parses_sample_export`:
```python
        stats, _dob = parse_export(db, xml_path)
```

In `test_type_filter`:
```python
        parse_export(db, xml_path, type_filter={"step_counts"})
```
(No change needed -- the return value is unused.)

Actually, Python will error if you call a function returning a tuple and don't unpack. No it won't -- you can ignore the return value. But `stats = parse_export(...)` will assign the tuple to `stats`, so accessing `stats["skipped"]` will fail. Update all four:

`test_parses_sample_export`:
```python
        stats, _dob = parse_export(db, xml_path)
```

`test_type_filter`:
```python
        _stats, _dob = parse_export(db, xml_path, type_filter={"step_counts"})
```

`test_since_filter`:
```python
        _stats, _dob = parse_export(db, xml_path, since="2024-03-15")
```

`test_returns_stats`:
```python
        stats, _dob = parse_export(db, xml_path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_parser.py::TestExtractDateOfBirth -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest`
Expected: all tests pass (call sites updated)

- [ ] **Step 7: Commit**

```bash
git add src/mosaic/parser.py src/mosaic/cli.py tests/test_parser.py
git commit -m "feat(parser): extract date of birth from Me element"
```

---

### Task 4: Implement `compute_hr_zones`

**Files:**
- Modify: `src/mosaic/parser.py` (add `compute_hr_zones` function)
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_parser.py`:

```python
from mosaic.parser import compute_hr_zones

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parser.py::TestComputeHrZones -v`
Expected: FAIL with `ImportError: cannot import name 'compute_hr_zones'`

- [ ] **Step 3: Implement compute_hr_zones**

Add to `src/mosaic/parser.py`:

```python
def _estimate_max_hr(date_of_birth: str) -> int:
    """Estimate max HR using Tanaka formula: 208 - 0.7 * age."""
    from datetime import date

    birth = date.fromisoformat(date_of_birth)
    today = date.today()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    return int(208 - 0.7 * age)


def compute_hr_zones(
    conn: _duckdb.DuckDBPyConnection,
    max_hr: int | None = None,
    date_of_birth: str | None = None,
) -> int:
    """Compute HR zones for each workout from overlapping heart_rate_samples.

    Uses max_hr if provided, otherwise estimates from date_of_birth.
    Returns the number of zone rows inserted.
    """
    if max_hr is None and date_of_birth is not None:
        max_hr = _estimate_max_hr(date_of_birth)
    if max_hr is None:
        print("  hr zones: skipped (no --max-hr and no date of birth in export)", file=sys.stderr)
        return 0

    result = conn.sql(f"""
        INSERT INTO workout_hr_zones
        SELECT
            workout_start,
            workout_type,
            CASE
                WHEN hr < {max_hr} * 0.6 THEN 1
                WHEN hr < {max_hr} * 0.7 THEN 2
                WHEN hr < {max_hr} * 0.8 THEN 3
                WHEN hr < {max_hr} * 0.9 THEN 4
                ELSE 5
            END AS zone,
            SUM(sample_seconds) AS seconds,
            source_name
        FROM (
            SELECT
                w.start_date AS workout_start,
                w.workout_type,
                w.source_name,
                h.value AS hr,
                EXTRACT(EPOCH FROM (
                    h.end_date::TIMESTAMP - h.start_date::TIMESTAMP
                )) AS sample_seconds
            FROM workouts w
            JOIN heart_rate_samples h
                ON h.start_date >= w.start_date
                AND h.start_date < w.end_date
            WHERE EXTRACT(EPOCH FROM (
                h.end_date::TIMESTAMP - h.start_date::TIMESTAMP
            )) > 0
        ) sub
        GROUP BY workout_start, workout_type, zone, source_name
    """)

    count_row = conn.sql("SELECT COUNT(*) FROM workout_hr_zones").fetchone()
    count: int = count_row[0] if count_row else 0
    print(f"  hr zones: {count} rows (max HR = {max_hr} bpm)", file=sys.stderr)
    return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_parser.py::TestComputeHrZones -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/mosaic/parser.py tests/test_parser.py
git commit -m "feat(parser): implement compute_hr_zones from real HR data"
```

---

### Task 5: Add `--max-hr` CLI flag and wire the pipeline

**Files:**
- Modify: `src/mosaic/cli.py:53-164`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::TestMaxHrFlag -v`
Expected: FAIL -- `--max-hr` flag not recognized

- [ ] **Step 3: Add flag and wire pipeline**

In `src/mosaic/cli.py`:

1. Add `--max-hr` argparse argument after `--batch-size`:
```python
    parser.add_argument(
        "--max-hr", type=int, default=None, help="Max heart rate for zone calculation (default: estimate from DOB)"
    )
```

2. Add import at top of file:
```python
from mosaic.parser import compute_hr_zones, parse_export
```

(Update the existing `from mosaic.parser import parse_export` to also import `compute_hr_zones`.)

3. After `parse_export` and before `create_views`, add zone computation:
```python
        stats, date_of_birth = parse_export(
            conn,
            xml_path,
            type_filter=type_filter,
            since=args.since,
            batch_size=args.batch_size,
        )

        # Compute HR zones from real heart rate data
        compute_hr_zones(conn, max_hr=args.max_hr, date_of_birth=date_of_birth)

        # Create views
        create_views(conn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::TestMaxHrFlag -v`
Expected: FAIL -- fixture doesn't have DOB or overlapping HR samples yet (handled in Task 6)

Note: This test depends on the fixture update in Task 6. Mark this as a pending integration -- move to Task 6.

- [ ] **Step 5: Run existing tests to verify nothing else broke**

Run: `uv run pytest tests/test_cli.py -v -k "not MaxHr"`
Expected: all existing CLI tests pass

- [ ] **Step 6: Commit**

```bash
git add src/mosaic/cli.py
git commit -m "feat(cli): add --max-hr flag and wire HR zone computation"
```

---

### Task 6: Update fixture and run integration tests

**Files:**
- Modify: `tests/fixtures/sample_export.xml`
- Modify: `tests/test_cli.py` (verify TestMaxHrFlag now passes)

- [ ] **Step 1: Update fixture XML**

In `tests/fixtures/sample_export.xml`, update the `<Me>` element to include DOB:

Old:
```xml
 <Me HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale"/>
```

New:
```xml
 <Me HKCharacteristicTypeIdentifierDateOfBirth="1990-05-15"
     HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale"/>
```

Add HR samples that overlap the existing workout (09:00-09:30). Insert them after the existing HeartRate record and before the HRV record:

```xml
 <Record type="HKQuantityTypeIdentifierHeartRate"
  sourceName="Apple Watch" sourceVersion="10.3"
  unit="count/min" value="125"
  startDate="2024-03-15 09:00:00 -0600"
  endDate="2024-03-15 09:10:00 -0600"
  creationDate="2024-03-15 09:10:05 -0600"/>
 <Record type="HKQuantityTypeIdentifierHeartRate"
  sourceName="Apple Watch" sourceVersion="10.3"
  unit="count/min" value="145"
  startDate="2024-03-15 09:10:00 -0600"
  endDate="2024-03-15 09:20:00 -0600"
  creationDate="2024-03-15 09:20:05 -0600"/>
 <Record type="HKQuantityTypeIdentifierHeartRate"
  sourceName="Apple Watch" sourceVersion="10.3"
  unit="count/min" value="162"
  startDate="2024-03-15 09:20:00 -0600"
  endDate="2024-03-15 09:30:00 -0600"
  creationDate="2024-03-15 09:30:05 -0600"/>
```

- [ ] **Step 2: Update TestParseExport.test_parses_sample_export counts**

The fixture now has 4 HR records (1 original + 3 new). Update the assertion in `test_parses_sample_export`:

```python
        assert db.sql("SELECT COUNT(*) FROM heart_rate_samples").fetchone()[0] == 4
```

- [ ] **Step 3: Run the full test suite including MaxHrFlag tests**

Run: `uv run pytest -v`
Expected: all tests pass, including `TestMaxHrFlag`

- [ ] **Step 4: Verify zone computation with the fixture data**

Add a verification test to `tests/test_cli.py`:

```python
class TestHrZoneIntegration:
    def test_zones_match_expected_classification(self, tmp_path: Path) -> None:
        """Verify fixture HR samples are classified correctly.

        Fixture workout: 09:00-09:30, DOB: 1990-05-15 -> age 33 -> max HR 184
        Z1: <110, Z2: 110-129, Z3: 129-147, Z4: 147-166, Z5: 166+
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
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/sample_export.xml tests/test_parser.py tests/test_cli.py
git commit -m "test: add fixture HR samples and integration tests for HR zones"
```

---

### Task 7: Update dashboard and export for new view shape

**Files:**
- Modify: `dashboard.html:773` (DuckDB-WASM query)
- Modify: `dashboard.html:1441-1445` (hrData mapping in buildCardioDetail)
- Modify: `dashboard.html:2065-2069` (sidebar hrData mapping)
- Modify: `src/mosaic/export.py:146-147` (hrzones JSON export query)
- Test: `tests/test_export.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_export.py`:

```python
class TestHrzonesExport:
    def test_hrzones_includes_total(self, db: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        create_tables(db)
        db.sql("""
            INSERT INTO workout_hr_zones VALUES
            ('2024-01-15 09:00:00-06', 'running', 2, 1200, 'Watch'),
            ('2024-01-15 09:00:00-06', 'running', 4, 300, 'Watch')
        """)
        create_views(db)
        out = tmp_path / "test.json"
        export_json(db, out)
        data = json.loads(out.read_text())
        assert len(data["hrzones"]) == 1
        row = data["hrzones"][0]
        assert "total" in row
        assert row["z2"] == 20.0
        assert row["z4"] == 5.0
        assert row["total"] == 25.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export.py::TestHrzonesExport -v`
Expected: FAIL -- query doesn't select `total`

- [ ] **Step 3: Update export.py hrzones query**

In `src/mosaic/export.py`, update the hrzones query:

Old:
```python
        "hrzones": _query(
            conn, "SELECT date AS d, z2, z4 FROM dashboard_hrzones ORDER BY date"
        ),
```

New:
```python
        "hrzones": _query(
            conn, "SELECT date AS d, z2, z4, total FROM dashboard_hrzones ORDER BY date"
        ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_export.py::TestHrzonesExport -v`
Expected: PASS

- [ ] **Step 5: Update dashboard.html DuckDB-WASM query**

In `dashboard.html`, line 773, update the hrzones query:

Old:
```javascript
      query(conn, "SELECT date AS d, z2, z4 FROM dashboard_hrzones"),
```

New:
```javascript
      query(conn, "SELECT date AS d, z2, z4, total FROM dashboard_hrzones"),
```

- [ ] **Step 6: Update dashboard.html hrData mapping in buildCardioDetail**

In `dashboard.html`, around line 1441-1446, update the `hrData` mapping:

Old:
```javascript
  const hrData = data.hrzones.map(d => ({
    d: parseDate(d.d),
    z2: d.z2,
    z4: d.z4,
    other: Math.max(0, (data.exercise.find(e => e.d === d.d)?.v || 0) - d.z2 - d.z4)
  }));
```

New:
```javascript
  const hrData = data.hrzones.map(d => ({
    d: parseDate(d.d),
    z2: d.z2,
    z4: d.z4,
    other: Math.max(0, (d.total || 0) - d.z2 - d.z4)
  }));
```

- [ ] **Step 7: Update dashboard.html sidebar hrData mapping**

In `dashboard.html`, around line 2065-2069, update the sidebar `hrData` mapping:

Old:
```javascript
  const hrData = data.hrzones.map(d => ({
    d: parseDate(d.d),
    z2: d.z2,
    z4: d.z4,
  }));
```

New:
```javascript
  const hrData = data.hrzones.map(d => ({
    d: parseDate(d.d),
    z2: d.z2,
    z4: d.z4,
    total: d.total || 0,
  }));
```

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
git add src/mosaic/export.py dashboard.html tests/test_export.py
git commit -m "feat(dashboard): update hrzones to use real zone data with total column"
```

---

### Task 8: Re-parse real data and verify

- [ ] **Step 1: Re-parse Michelle's export with the new pipeline**

Run: `uv run mosaic "/Users/mpellon/Downloads/export(1).zip" --output data/health.duckdb --force`

Expected: output includes a line like `hr zones: N rows (max HR = XXX bpm)` showing zones were computed.

- [ ] **Step 2: Verify zone data in DuckDB**

Run: `uv run python -c "import duckdb; c=duckdb.connect('data/health.duckdb',read_only=True); print(c.sql('SELECT * FROM dashboard_hrzones ORDER BY date DESC LIMIT 5').fetchall())"`

Expected: rows with date, z2, z4, total -- real values, not fabricated.

- [ ] **Step 3: Regenerate embedded_data.json**

Run: `uv run mosaic "/Users/mpellon/Downloads/export(1).zip" --output data/health.duckdb --force --json data/embedded_data.json`

- [ ] **Step 4: Verify dashboard in browser**

Open `http://localhost:8080/dashboard.html` and check the HR zone chart in the Cardiovascular Detail section. Bars should show real zone distribution.

- [ ] **Step 5: Run type check and lint**

Run: `uv run pyright && uv run ruff check`
Expected: no errors

- [ ] **Step 6: Final commit if any fixups needed**

```bash
git add -A && git commit -m "chore: regenerate embedded data with real HR zones"
```
