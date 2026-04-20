"""Local web server for the Mosaic dashboard with API endpoints."""
# ABOUTME: Serves the dashboard and provides a JSON API for reading/writing
# ABOUTME: profile data to DuckDB. Replaces python3 -m http.server.

import json
import os
import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import duckdb

DB_PATH = os.environ.get("MOSAIC_DB", "data/health.duckdb")


class MosaicHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves static files and profile API endpoints."""

    def do_GET(self) -> None:
        if self.path == "/api/profile":
            self._handle_get_profile()
        elif self.path == "/api/readiness":
            self._handle_get_readiness()
        else:
            super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/profile":
            self._handle_post_profile()
        elif self.path == "/api/import":
            self._handle_import()
        else:
            self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _handle_get_profile(self) -> None:
        try:
            conn = duckdb.connect(DB_PATH, read_only=True)
            try:
                rows = conn.sql("SELECT key, value FROM athlete_profile").fetchall()
                profile = dict(rows)
            except duckdb.CatalogException:
                profile = {}
            finally:
                conn.close()
            self._json_response(profile)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_post_profile(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)

            conn = duckdb.connect(DB_PATH)
            try:
                # Ensure table exists
                conn.sql("""
                    CREATE TABLE IF NOT EXISTS athlete_profile (
                        key   VARCHAR NOT NULL PRIMARY KEY,
                        value VARCHAR NOT NULL
                    )
                """)
                for key, value in data.items():
                    if value:
                        conn.execute(
                            "INSERT OR REPLACE INTO athlete_profile VALUES (?, ?)",
                            [str(key), str(value)],
                        )
                    else:
                        conn.execute(
                            "DELETE FROM athlete_profile WHERE key = ?",
                            [str(key)],
                        )
            finally:
                conn.close()

            self._json_response({"status": "saved", "fields": len(data)})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_import(self) -> None:
        import tempfile

        from mosaic.cli import resolve_xml_path
        from mosaic.fhir import parse_clinical_records
        from mosaic.parser import compute_hr_zones, parse_export
        from mosaic.schema import create_tables, create_views, truncate_tables

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            # Save uploaded file to temp location
            suffix = ".zip"
            content_type = self.headers.get("Content-Type", "")
            if "xml" in content_type:
                suffix = ".xml"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="mosaic_upload_")
            tmp.write(body)
            tmp.close()
            tmp_path = Path(tmp.name)

            try:
                xml_path, clinical_dir, cleanup = resolve_xml_path(tmp_path)

                # Preserve existing profile before truncating
                profile: dict[str, str] = {}
                try:
                    conn = duckdb.connect(DB_PATH, read_only=True)
                    rows = conn.sql("SELECT key, value FROM athlete_profile").fetchall()
                    profile = dict(rows)
                    conn.close()
                except Exception:
                    pass

                conn = duckdb.connect(DB_PATH)
                create_tables(conn)
                truncate_tables(conn)

                stats, dob = parse_export(conn, xml_path)
                compute_hr_zones(conn, max_hr=None, date_of_birth=dob)
                create_views(conn)

                if clinical_dir:
                    parse_clinical_records(conn, clinical_dir)

                # Restore profile
                for key, value in profile.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO athlete_profile VALUES (?, ?)",
                        [key, value],
                    )

                total = stats.get("total", 0)
                labs = conn.sql("SELECT COUNT(*) FROM clinical_labs").fetchone()
                lab_count: int = labs[0] if labs else 0
                conn.close()

                if cleanup:
                    cleanup()

                self._json_response({
                    "status": "imported",
                    "records": total,
                    "labs": lab_count,
                })
            finally:
                tmp_path.unlink(missing_ok=True)

        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_get_readiness(self) -> None:
        try:
            from mosaic.readiness import compute_readiness

            conn = duckdb.connect(DB_PATH, read_only=True)
            try:
                result = compute_readiness(conn)
            finally:
                conn.close()
            self._json_response(result)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def log_message(self, fmt: str, *args: object) -> None:  # type: ignore[override]
        if len(args) >= 1 and isinstance(args[0], str) and "/api/" in args[0]:
            super().log_message(fmt, *args)


def main() -> None:
    """Start the Mosaic web server."""
    port = int(os.environ.get("MOSAIC_PORT", "8080"))

    if not Path(DB_PATH).exists():
        print(f"Warning: {DB_PATH} not found. Parse your data first.", file=sys.stderr)

    handler = partial(MosaicHandler, directory=".")
    server = HTTPServer(("", port), handler)
    print(f"Mosaic → http://localhost:{port}/dashboard.html", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
