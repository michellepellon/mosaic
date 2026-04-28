"""Tests for regimen-related web.py endpoints."""

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path
from typing import Any

import duckdb
import pytest

from mosaic import web
from mosaic.schema import create_tables, create_views


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """Start MosaicHandler against a fresh temp DuckDB on a free port."""
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    create_tables(conn)
    create_views(conn)
    conn.close()

    monkeypatch.setattr(web, "DB_PATH", str(db_path))

    httpd = HTTPServer(("127.0.0.1", 0), web.MosaicHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()


def _request(
    port: int, method: str, path: str, body: object | None = None
) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_regimens_get_empty(server: int):
    status, body = _request(server, "GET", "/api/regimens")
    assert status == 200
    assert body == []


def test_regimens_post_replace_all(server: int):
    payload = [
        {"name": "Creatine", "brand": "Thorne", "category": "supplement",
         "dose_amount": 5.0, "dose_unit": "g", "schedule": "morning",
         "start_date": "2025-09-12", "end_date": None, "notes": ""},
        {"name": "Magnesium", "brand": "Thorne", "category": "supplement",
         "dose_amount": 400.0, "dose_unit": "mg", "schedule": "both",
         "start_date": "2026-01-15", "end_date": None, "notes": ""},
    ]
    status, body = _request(server, "POST", "/api/regimens", payload)
    assert status == 200
    assert body == {"status": "saved", "regimens": 2}

    status, body = _request(server, "GET", "/api/regimens")
    assert status == 200
    assert isinstance(body, list)
    regimen_list: list[dict[str, Any]] = body  # type: ignore[assignment]
    assert {item["name"] for item in regimen_list} == {"Creatine", "Magnesium"}


def test_regimens_post_invalid_json_returns_400(server: int):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server}/api/regimens",
        data=b"not json",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 400
