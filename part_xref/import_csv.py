"""CSV parsing for bulk part number import."""

from __future__ import annotations

import csv
import io


def parse_part_numbers_csv(content: str) -> list[str]:
    """Extract part numbers from CSV content.

    Accepts a single column of part numbers, with or without a header row.
    Recognised headers: part_number, part number, part, number.
    """
    if not content.strip():
        return []

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return []

    part_numbers: list[str] = []
    start_index = 0

    first_cell = rows[0][0].strip().lower() if rows[0] else ""
    if first_cell in {"part_number", "part number", "part", "number"}:
        start_index = 1

    seen: set[str] = set()
    for row in rows[start_index:]:
        if not row:
            continue
        value = row[0].strip()
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        part_numbers.append(value)

    return part_numbers
