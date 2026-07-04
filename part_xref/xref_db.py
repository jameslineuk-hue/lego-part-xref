"""PostgreSQL persistence for curated part cross-reference entries."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from psycopg.rows import dict_row

from part_xref.config import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from part_xref.models import ALTERNATIVE_SOURCE_COLUMNS

logger = logging.getLogger(__name__)

_SOURCE_COLUMN_SQL = ",\n                    ".join(
    f"{column} VARCHAR(64)" for column in ALTERNATIVE_SOURCE_COLUMNS.values()
)


def source_column_values(
    *,
    brick_architect_part_number: Optional[str],
    alternative_part_numbers: dict[str, str],
) -> dict[str, Optional[str]]:
    """Resolve per-source column values from lookup result fields."""
    values = {
        column: alternative_part_numbers.get(source_key)
        for source_key, column in ALTERNATIVE_SOURCE_COLUMNS.items()
    }
    values["brick_architect_part_number"] = (
        brick_architect_part_number or values["brick_architect_part_number"]
    )
    return values


def migrate_source_columns(conn: psycopg.Connection) -> None:
    """Add per-source columns and backfill them from the JSON blob."""
    for column in ALTERNATIVE_SOURCE_COLUMNS.values():
        conn.execute(
            f"ALTER TABLE part_xrefs ADD COLUMN IF NOT EXISTS {column} VARCHAR(64)"
        )

    set_clauses = [
        (
            f"{column} = COALESCE("
            f"{column}, "
            f"NULLIF(alternative_part_numbers->>%s, '')"
            f")"
        )
        for source_key, column in ALTERNATIVE_SOURCE_COLUMNS.items()
    ]
    params = list(ALTERNATIVE_SOURCE_COLUMNS.keys())
    conn.execute(
        f"""
        UPDATE part_xrefs
        SET {", ".join(set_clauses)}
        """,
        params,
    )


class PartXrefStore:
    """Persistent store for part cross-reference lookup results."""

    def __init__(
        self,
        *,
        host: str = POSTGRES_HOST,
        port: int = POSTGRES_PORT,
        dbname: str = POSTGRES_DB,
        user: str = POSTGRES_USER,
        password: str = POSTGRES_PASSWORD,
    ) -> None:
        self._conninfo = (
            f"host={host} port={port} dbname={dbname} user={user} password={password}"
        )
        self._ensure_schema()

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM part_xrefs").fetchone()
        return int(row["count"])

    def exists(self, part_number: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM part_xrefs WHERE part_number = %s",
                (part_number,),
            ).fetchone()
        return row is not None

    def insert(
        self,
        part_number: str,
        *,
        brick_architect_part_number: Optional[str],
        alternative_part_numbers: dict[str, str],
    ) -> bool:
        """Insert a xref entry. Returns True if inserted, False if already exists."""
        columns = source_column_values(
            brick_architect_part_number=brick_architect_part_number,
            alternative_part_numbers=alternative_part_numbers,
        )
        column_names = ", ".join(columns.keys())
        placeholders = ", ".join(["%s"] * len(columns))

        with self._connect() as conn:
            row = conn.execute(
                f"""
                INSERT INTO part_xrefs (
                    part_number,
                    alternative_part_numbers,
                    {column_names}
                )
                VALUES (%s, %s::jsonb, {placeholders})
                ON CONFLICT (part_number) DO NOTHING
                RETURNING id
                """,
                (
                    part_number,
                    json.dumps(alternative_part_numbers),
                    *columns.values(),
                ),
            ).fetchone()
        inserted = row is not None
        if inserted:
            logger.info("Xref saved", extra={"part_number": part_number})
        else:
            logger.info("Xref already exists", extra={"part_number": part_number})
        return inserted

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS part_xrefs (
                    id SERIAL PRIMARY KEY,
                    part_number VARCHAR(64) NOT NULL UNIQUE,
                    {_SOURCE_COLUMN_SQL},
                    alternative_part_numbers JSONB NOT NULL DEFAULT '{{}}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            migrate_source_columns(conn)

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(self._conninfo, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
