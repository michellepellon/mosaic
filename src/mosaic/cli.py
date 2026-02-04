"""CLI entry point for mosaic."""

import argparse
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import duckdb

from mosaic.export import export_json
from mosaic.parser import parse_export
from mosaic.schema import TABLE_NAMES, create_tables, create_views, truncate_tables


def resolve_xml_path(input_path: Path) -> tuple[Path, Callable[[], None] | None]:
    """Resolve input to an export.xml path.

    Returns (xml_path, cleanup_fn). cleanup_fn is None if no temp dir was created.
    """
    if not input_path.exists():
        print(f"Error: {input_path} does not exist", file=sys.stderr)
        raise SystemExit(1)

    if input_path.suffix == ".xml":
        return input_path, None

    if input_path.suffix == ".zip":
        tmp_dir = tempfile.mkdtemp(prefix="mosaic_")
        tmp_path = Path(tmp_dir)
        with zipfile.ZipFile(input_path, "r") as zf:
            # Look for export.xml anywhere in the archive
            xml_names = [n for n in zf.namelist() if n.endswith("export.xml")]
            if not xml_names:
                print("Error: No export.xml found in zip archive", file=sys.stderr)
                raise SystemExit(1)
            zf.extract(xml_names[0], tmp_path)
            extracted = tmp_path / xml_names[0]

        def cleanup() -> None:
            import shutil

            shutil.rmtree(tmp_path, ignore_errors=True)

        return extracted, cleanup

    print(f"Error: {input_path} must be a .xml or .zip file", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    """Parse Apple Health exports into DuckDB."""
    parser = argparse.ArgumentParser(
        prog="mosaic",
        description="Parse Apple Health Data exports into DuckDB",
    )
    parser.add_argument("input", type=Path, help="Path to export.zip or export.xml")
    parser.add_argument(
        "--output", type=Path, default=Path("health.duckdb"), help="Output .duckdb file path"
    )
    parser.add_argument(
        "--types",
        type=str,
        default=None,
        help="Comma-separated table names to ingest (default: all)",
    )
    parser.add_argument(
        "--since", type=str, default=None, help="Only ingest records from this date"
    )
    parser.add_argument(
        "--force", action="store_true", help="Truncate existing tables before import"
    )
    parser.add_argument(
        "--batch-size", type=int, default=50_000, help="Rows per batch flush (default: 50000)"
    )
    parser.add_argument(
        "--labs", type=Path, default=None, help="Path to CSV with lab results"
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="Export dashboard data to JSON file"
    )

    args = parser.parse_args(argv)

    # Validate --types
    type_filter: set[str] | None = None
    if args.types:
        type_filter = set(args.types.split(","))
        invalid = type_filter - TABLE_NAMES
        if invalid:
            print(
                f"Error: Unknown table names: {', '.join(sorted(invalid))}",
                file=sys.stderr,
            )
            print(f"Valid names: {', '.join(sorted(TABLE_NAMES))}", file=sys.stderr)
            raise SystemExit(1)

    # Resolve input
    xml_path, cleanup = resolve_xml_path(args.input)

    try:
        start_time = time.monotonic()

        # Initialize DuckDB
        conn = duckdb.connect(str(args.output))
        create_tables(conn)
        if args.force:
            truncate_tables(conn)

        # Parse and ingest
        print(f"Parsing {xml_path}...", file=sys.stderr)
        stats = parse_export(
            conn,
            xml_path,
            type_filter=type_filter,
            since=args.since,
            batch_size=args.batch_size,
        )

        # Create views
        create_views(conn)

        # Import lab results if provided
        if args.labs:
            if not args.labs.exists():
                print(f"Error: {args.labs} does not exist", file=sys.stderr)
                raise SystemExit(1)
            conn.sql(
                "INSERT INTO clinical_labs SELECT * FROM read_csv_auto(?)",
                params=[str(args.labs)],
            )

        # Export JSON if requested
        if args.json:
            export_json(conn, args.json)
            print(f"  json: {args.json}", file=sys.stderr)

        elapsed = time.monotonic() - start_time

        # Summary
        print("\n--- Import Summary ---", file=sys.stderr)
        for table_name in sorted(TABLE_NAMES):
            count = stats.get(table_name, 0)
            if count > 0:
                print(f"  {table_name}: {count:,} rows", file=sys.stderr)
        print(f"  total: {stats.get('total', 0):,} rows", file=sys.stderr)
        print(f"  skipped: {stats.get('skipped', 0):,}", file=sys.stderr)
        if args.labs:
            row = conn.sql("SELECT COUNT(*) FROM clinical_labs").fetchone()
            lab_count: int = row[0] if row else 0
            print(f"  clinical_labs: {lab_count:,} rows (from {args.labs})", file=sys.stderr)
        print(f"  elapsed: {elapsed:.1f}s", file=sys.stderr)
        db_size = args.output.stat().st_size
        print(
            f"  output: {args.output} ({db_size / 1024 / 1024:.1f} MB)", file=sys.stderr
        )

        conn.close()
    finally:
        if cleanup:
            cleanup()
