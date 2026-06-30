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

logger = logging.getLogger(__name__)


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
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO part_xrefs (
                    part_number,
                    brick_architect_part_number,
                    alternative_part_numbers
                )
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (part_number) DO NOTHING
                RETURNING id
                """,
                (
                    part_number,
                    brick_architect_part_number,
                    json.dumps(alternative_part_numbers),
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
                """
                CREATE TABLE IF NOT EXISTS part_xrefs (
                    id SERIAL PRIMARY KEY,
                    part_number VARCHAR(64) NOT NULL UNIQUE,
                    brick_architect_part_number VARCHAR(64),
                    alternative_part_numbers JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(self._conninfo, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
