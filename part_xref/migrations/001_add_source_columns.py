"""Add per-source part number columns to part_xrefs and backfill from JSON.

Run after deploying code that expects dedicated source columns:

    python -m part_xref.migrations.001_add_source_columns
"""

from __future__ import annotations

import logging
import sys

import psycopg
from psycopg.rows import dict_row

from part_xref.config import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from part_xref.xref_db import migrate_source_columns

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
    logger = logging.getLogger(__name__)

    conninfo = (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} "
        f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    )

    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        logger.info("Applying migration 001_add_source_columns")
        migrate_source_columns(conn)
        conn.commit()
        row = conn.execute("SELECT COUNT(*) AS count FROM part_xrefs").fetchone()
        logger.info(
            "Migration complete; %s part_xrefs row(s) present",
            row["count"] if row else 0,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
