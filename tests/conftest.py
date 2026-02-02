"""Shared test fixtures."""

import duckdb
import pytest


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection for testing."""
    return duckdb.connect(":memory:")
