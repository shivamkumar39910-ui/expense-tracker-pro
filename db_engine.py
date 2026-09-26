"""
Expense Tracker Pro 2.0 - Universal Database Abstraction Layer (db_engine.py)
Supports both PostgreSQL (production via DATABASE_URL) and SQLite (development/fallback).
Provides seamless query translation (? -> %s), Dict+Tuple row access, JSON-safe Decimals, and lastrowid emulation.
"""

import os
import re
import sqlite3
from collections.abc import Mapping
from decimal import Decimal
from typing import Optional, Any, Tuple, List, Dict

# Check for DATABASE_URL in environment
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "expenses.db")

def is_postgres() -> bool:
    return bool(DATABASE_URL)

def get_db_type() -> str:
    return "postgres" if is_postgres() else "sqlite"


# ==================================================
# PostgreSQL Compatibility Wrappers
# ==================================================

class PostgresRowWrapper(Mapping):
    """
    Wraps psycopg2 DictRow to provide:
    1. Dual access: by column name (row['amount']) and by index (row[0]).
    2. Automatic Decimal to float conversion for seamless JSON serialization in Flask.
    3. Full Mapping protocol: dict(row), row.get(), row.items(), row.keys(), 'key' in row.
    """
    def __init__(self, raw_row):
        self._raw = raw_row

    def __getitem__(self, key):
        val = self._raw[key]
        if isinstance(val, Decimal):
            return float(val)
        return val

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def keys(self):
        return self._raw.keys()

    def values(self):
        return [self[k] for k in self.keys()]

    def items(self):
        return [(k, self[k]) for k in self.keys()]

    def __iter__(self):
        return iter(self._raw.keys())

    def __len__(self):
        return len(self._raw.keys())

    def __contains__(self, key):
        return key in self._raw

    def __repr__(self):
        return f"<PostgresRow {dict(self)}>"


class PostgresCursorWrapper:
    """
    Wraps a psycopg2 cursor to provide:
    1. Automatic '?' to '%s' parameter placeholder conversion.
    2. Transparent cursor.lastrowid emulation via RETURNING id.
    3. Transparent translation of SQLite-specific functions (e.g. datetime('now') -> CURRENT_TIMESTAMP).
    4. Safe no-op for PRAGMA statements.
    """
    def __init__(self, raw_cursor):
        self._cursor = raw_cursor
        self.lastrowid: Optional[int] = None
        self._synthetic_returning = False

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def _translate_query(self, query: str) -> Tuple[str, bool]:
        """Translates SQLite syntax to PostgreSQL syntax."""
        q = query.strip()

        # Handle PRAGMA as no-op
        if q.upper().startswith("PRAGMA"):
            return "-- PRAGMA ignored in Postgres\nSELECT 1", False

        # Replace datetime('now') with CURRENT_TIMESTAMP
        q = re.sub(r"datetime\(\s*'now'\s*\)", "CURRENT_TIMESTAMP", q, flags=re.IGNORECASE)
        q = re.sub(r"date\(\s*'now'\s*\)", "CURRENT_DATE", q, flags=re.IGNORECASE)

        # Replace '?' with '%s' for psycopg2 parameters
        q = q.replace("?", "%s")

        # Emulate lastrowid for INSERT statements
        is_insert = q.upper().startswith("INSERT INTO") or "INSERT INTO" in q.upper()
        has_returning = "RETURNING" in q.upper()
        synthetic_returning = False

        if is_insert and not has_returning:
            # Append RETURNING id so we can capture cursor.lastrowid
            q_clean = q.rstrip("; \t\n")
            q = f"{q_clean} RETURNING id"
            synthetic_returning = True

        return q, synthetic_returning

    def execute(self, query: str, params: Any = None):
        translated_query, self._synthetic_returning = self._translate_query(query)

        if translated_query.strip().startswith("-- PRAGMA ignored"):
            self.lastrowid = None
            return self

        try:
            if params is not None:
                if isinstance(params, (list, tuple)):
                    self._cursor.execute(translated_query, tuple(params))
                else:
                    self._cursor.execute(translated_query, (params,))
            else:
                self._cursor.execute(translated_query)

            if self._synthetic_returning:
                try:
                    row = self._cursor.fetchone()
                    if row is not None:
                        self.lastrowid = row[0] if isinstance(row, (tuple, list)) else row.get("id")
                    else:
                        self.lastrowid = None
                except Exception:
                    self.lastrowid = None
            else:
                self.lastrowid = None

            return self
        except Exception as e:
            raise e

    def executemany(self, query: str, seq_of_params):
        translated_query, _ = self._translate_query(query)
        clean_q = re.sub(r"\s+RETURNING\s+id", "", translated_query, flags=re.IGNORECASE)
        return self._cursor.executemany(clean_q, seq_of_params)

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return PostgresRowWrapper(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [PostgresRowWrapper(r) for r in rows]

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size)
        return [PostgresRowWrapper(r) for r in rows]

    def close(self):
        self._cursor.close()

    def __iter__(self):
        for r in self._cursor:
            yield PostgresRowWrapper(r)


class PostgresConnectionWrapper:
    """Wraps a psycopg2 connection to provide cursor() with PostgresCursorWrapper."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        import psycopg2.extras
        raw_cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        return PostgresCursorWrapper(raw_cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, query: str, params: Any = None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()


# ==================================================
# Universal Connection Factory
# ==================================================

def get_db_connection():
    """
    Universal database connection factory.
    Returns a connection to PostgreSQL if DATABASE_URL is configured,
    otherwise returns a connection to SQLite (expenses.db).
    Both connections support standard cursor(), commit(), rollback(), and row_factory access.
    """
    if is_postgres():
        import psycopg2
        import psycopg2.extras
        try:
            raw_conn = psycopg2.connect(DATABASE_URL)
            return PostgresConnectionWrapper(raw_conn)
        except Exception as e:
            print(f"[DB ENGINE WARNING] PostgreSQL connection failed: {e}. Falling back to SQLite.")
            return _get_sqlite_connection()
    else:
        return _get_sqlite_connection()


def _get_sqlite_connection():
    conn = sqlite3.connect(SQLITE_DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn
