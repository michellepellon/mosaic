"""Local web server for the Mosaic dashboard with API endpoints."""
# ABOUTME: Serves the dashboard and provides a JSON API for reading/writing
# ABOUTME: profile data to DuckDB. Replaces python3 -m http.server.

import json
import os
import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, cast

import duckdb

DB_PATH = os.environ.get("MOSAIC_DB", "data/health.duckdb")


class MosaicHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves static files and profile API endpoints."""

    def do_GET(self) -> None:
        if self.path == "/api/profile":
            self._handle_get_profile()
        elif self.path == "/api/readiness":
            self._handle_get_readiness()
        elif self.path == "/api/training-plan":
            self._handle_get_training_plan()
        elif self.path == "/api/goals":
            self._handle_get_goals()
        elif self.path == "/api/regimens":
            self._handle_get_regimens()
        elif self.path.startswith("/api/regimen-events"):
            self._handle_get_regimen_events()
        else:
            super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/profile":
            self._handle_post_profile()
        elif self.path == "/api/import":
            self._handle_import()
        elif self.path == "/api/training-plan":
            self._handle_post_training_plan()
        elif self.path == "/api/goals":
            self._handle_post_goals()
        elif self.path == "/api/regimens":
            self._handle_post_regimens()
        elif self.path == "/api/regimen-events":
            self._handle_post_regimen_event()
        else:
            self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_DELETE(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/regimen-events":
            self._handle_delete_regimen_event()
        else:
            self.send_error(404)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS"
        )
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

    def _handle_get_training_plan(self) -> None:
        try:
            conn = duckdb.connect(DB_PATH, read_only=True)
            try:
                rows = conn.sql(
                    "SELECT id, name, phase, start_date, end_date, "
                    "volume_target, notes "
                    "FROM training_blocks ORDER BY start_date"
                ).fetchall()
                blocks = [
                    {
                        "id": r[0], "name": r[1], "phase": r[2],
                        "start_date": str(r[3]), "end_date": str(r[4]),
                        "volume_target": r[5], "notes": r[6],
                    }
                    for r in rows
                ]
            except duckdb.CatalogException:
                blocks = []
            finally:
                conn.close()
            self._json_response(blocks)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_post_training_plan(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            conn = duckdb.connect(DB_PATH)
            try:
                conn.sql("""
                    CREATE TABLE IF NOT EXISTS training_blocks (
                        id INTEGER NOT NULL PRIMARY KEY,
                        name VARCHAR NOT NULL, phase VARCHAR NOT NULL,
                        start_date DATE NOT NULL, end_date DATE NOT NULL,
                        volume_target INTEGER, notes VARCHAR)
                """)
                conn.sql("DELETE FROM training_blocks")
                for i, block in enumerate(data):
                    conn.execute(
                        "INSERT INTO training_blocks VALUES "
                        "(?, ?, ?, ?, ?, ?, ?)",
                        [
                            i, block["name"], block["phase"],
                            block["start_date"], block["end_date"],
                            block.get("volume_target"),
                            block.get("notes", ""),
                        ],
                    )
            finally:
                conn.close()
            self._json_response({"status": "saved", "blocks": len(data)})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_get_goals(self) -> None:
        try:
            conn = duckdb.connect(DB_PATH, read_only=True)
            try:
                rows = conn.sql(
                    "SELECT id, name, target_date, metric, "
                    "target_value, notes FROM goals ORDER BY target_date"
                ).fetchall()
                goals = [
                    {
                        "id": r[0], "name": r[1],
                        "target_date": str(r[2]) if r[2] else None,
                        "metric": r[3], "target_value": r[4],
                        "notes": r[5],
                    }
                    for r in rows
                ]
            except duckdb.CatalogException:
                goals = []
            finally:
                conn.close()
            self._json_response(goals)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_post_goals(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            conn = duckdb.connect(DB_PATH)
            try:
                conn.sql("""
                    CREATE TABLE IF NOT EXISTS goals (
                        id INTEGER NOT NULL PRIMARY KEY,
                        name VARCHAR NOT NULL, target_date DATE,
                        metric VARCHAR, target_value DOUBLE,
                        notes VARCHAR)
                """)
                conn.sql("DELETE FROM goals")
                for i, goal in enumerate(data):
                    conn.execute(
                        "INSERT INTO goals VALUES (?, ?, ?, ?, ?, ?)",
                        [
                            i, goal["name"],
                            goal.get("target_date"),
                            goal.get("metric"),
                            goal.get("target_value"),
                            goal.get("notes", ""),
                        ],
                    )
            finally:
                conn.close()
            self._json_response({"status": "saved", "goals": len(data)})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_get_regimens(self) -> None:
        try:
            conn = duckdb.connect(DB_PATH, read_only=True)
            try:
                rows = conn.sql(
                    "SELECT id, name, brand, category, dose_amount, "
                    "dose_unit, schedule, start_date, end_date, notes "
                    "FROM regimens ORDER BY start_date"
                ).fetchall()
                regimens = [
                    {
                        "id": r[0], "name": r[1], "brand": r[2],
                        "category": r[3], "dose_amount": r[4],
                        "dose_unit": r[5], "schedule": r[6],
                        "start_date": str(r[7]),
                        "end_date": str(r[8]) if r[8] else None,
                        "notes": r[9],
                    }
                    for r in rows
                ]
            except duckdb.CatalogException:
                regimens = []
            finally:
                conn.close()
            self._json_response(regimens)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_post_regimens(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            try:
                data: Any = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._json_response({"error": "invalid json"}, 400)
                return
            if not isinstance(data, list):
                self._json_response(
                    {"error": "expected list of regimens"}, 400
                )
                return

            conn = duckdb.connect(DB_PATH)
            try:
                from mosaic.schema import create_tables
                create_tables(conn)
                conn.sql("DELETE FROM regimens")
                regimen_list: list[dict[str, Any]] = cast(list[dict[str, Any]], data)
                for i, regimen in enumerate(regimen_list):
                    conn.execute(
                        "INSERT INTO regimens VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            i, regimen["name"], regimen.get("brand"), regimen["category"],
                            regimen.get("dose_amount"), regimen.get("dose_unit"),
                            regimen["schedule"], regimen["start_date"],
                            regimen.get("end_date"), regimen.get("notes", ""),
                        ],
                    )
            finally:
                conn.close()
            self._json_response({"status": "saved", "regimens": len(regimen_list)})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_get_regimen_events(self) -> None:
        try:
            from datetime import date, timedelta
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            since = qs.get("since", [None])[0]
            if since is None:
                since = (date.today() - timedelta(days=30)).isoformat()

            conn = duckdb.connect(DB_PATH, read_only=True)
            try:
                rows = conn.sql(
                    "SELECT id, regimen_id, event_date, event_type, slot, "
                    "substance, brand, dose_amount, dose_unit, notes "
                    "FROM regimen_events WHERE event_date >= ? "
                    "ORDER BY event_date DESC, id DESC",
                    params=[since],
                ).fetchall()
                events = [
                    {
                        "id": r[0], "regimen_id": r[1],
                        "event_date": str(r[2]), "event_type": r[3],
                        "slot": r[4], "substance": r[5], "brand": r[6],
                        "dose_amount": r[7], "dose_unit": r[8],
                        "notes": r[9],
                    }
                    for r in rows
                ]
            except duckdb.CatalogException:
                events = []
            finally:
                conn.close()
            self._json_response(events)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_post_regimen_event(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            try:
                data: Any = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._json_response({"error": "invalid json"}, 400)
                return
            if not isinstance(data, dict):
                self._json_response({"error": "expected object"}, 400)
                return
            for required in ("event_date", "event_type"):
                if required not in data:
                    self._json_response(
                        {"error": f"missing field: {required}"}, 400
                    )
                    return

            conn = duckdb.connect(DB_PATH)
            try:
                from mosaic.schema import create_tables
                create_tables(conn)
                next_id_row = conn.sql(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM regimen_events"
                ).fetchone()
                new_id = next_id_row[0] if next_id_row else 1
                event_dict: dict[str, Any] = cast(dict[str, Any], data)
                conn.execute(
                    "INSERT INTO regimen_events VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        new_id, event_dict.get("regimen_id"), event_dict["event_date"],
                        event_dict["event_type"], event_dict.get("slot"),
                        event_dict.get("substance"), event_dict.get("brand"),
                        event_dict.get("dose_amount"), event_dict.get("dose_unit"),
                        event_dict.get("notes", ""),
                    ],
                )
            finally:
                conn.close()
            self._json_response({"id": new_id})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_delete_regimen_event(self) -> None:
        try:
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            id_str = qs.get("id", [None])[0]
            if id_str is None:
                self._json_response({"error": "missing id"}, 400)
                return
            try:
                event_id = int(id_str)
            except ValueError:
                self._json_response({"error": "id must be integer"}, 400)
                return

            conn = duckdb.connect(DB_PATH)
            try:
                conn.execute(
                    "DELETE FROM regimen_events WHERE id = ?", [event_id]
                )
            finally:
                conn.close()
            self._json_response({"status": "deleted"})
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

                conn = duckdb.connect(DB_PATH)
                create_tables(conn)
                truncate_tables(conn)

                stats, dob = parse_export(conn, xml_path)
                compute_hr_zones(conn, max_hr=None, date_of_birth=dob)
                create_views(conn)

                if clinical_dir:
                    parse_clinical_records(conn, clinical_dir)

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
