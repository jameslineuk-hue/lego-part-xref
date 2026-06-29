"""SQLite-backed cache for part cross-reference lookups."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from part_xref.config import CACHE_DB_PATH, CACHE_ENABLED, CACHE_TTL_SECONDS
from part_xref.scraper import ScrapeResult

logger = logging.getLogger(__name__)


class PartCrossReferenceCache:
    """Optional SQLite cache with TTL for scrape results."""

    def __init__(
        self,
        db_path: Path = CACHE_DB_PATH,
        *,
        enabled: bool = CACHE_ENABLED,
        ttl_seconds: int = CACHE_TTL_SECONDS,
    ) -> None:
        self.db_path = db_path
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        if self.enabled:
            self._ensure_schema()

    def get(self, part_number: str) -> Optional[ScrapeResult]:
        if not self.enabled:
            return None

        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload, created_at
                FROM part_xref_cache
                WHERE part_number = ?
                """,
                (part_number,),
            ).fetchone()

        if row is None:
            logger.info("Cache miss", extra={"part_number": part_number})
            return None

        created_at = float(row["created_at"])
        if now - created_at > self.ttl_seconds:
            logger.info("Cache expired", extra={"part_number": part_number})
            self.delete(part_number)
            return None

        result = self._deserialize(row["payload"])
        if result.found and not result.brick_architect_part_number:
            logger.info(
                "Cache stale (missing Brick Architect number)",
                extra={"part_number": part_number},
            )
            self.delete(part_number)
            return None

        logger.info("Cache hit", extra={"part_number": part_number})
        return result

    def set(self, result: ScrapeResult) -> None:
        if not self.enabled:
            return

        payload = self._serialize(result)
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO part_xref_cache (part_number, payload, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(part_number) DO UPDATE SET
                    payload = excluded.payload,
                    created_at = excluded.created_at
                """,
                (result.part_number, payload, now),
            )
        logger.info("Cache store", extra={"part_number": result.part_number})

    def delete(self, part_number: str) -> None:
        if not self.enabled:
            return
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM part_xref_cache WHERE part_number = ?",
                (part_number,),
            )

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS part_xref_cache (
                    part_number TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _serialize(result: ScrapeResult) -> str:
        return json.dumps(
            {
                "part_number": result.part_number,
                "brick_architect_part_number": result.brick_architect_part_number,
                "alternatives": result.alternatives,
                "found": result.found,
                "error": result.error,
            }
        )

    @staticmethod
    def _deserialize(payload: str) -> ScrapeResult:
        data = json.loads(payload)
        return ScrapeResult(
            part_number=data["part_number"],
            brick_architect_part_number=data.get("brick_architect_part_number"),
            alternatives=data.get("alternatives", {}),
            found=data.get("found", True),
            error=data.get("error"),
        )
