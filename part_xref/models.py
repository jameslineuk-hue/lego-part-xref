"""Pydantic models for the part cross-reference API."""

from typing import Optional

from pydantic import BaseModel, Field


class AlternativePartNumbers(BaseModel):
    """Alternative part numbers keyed by external source."""

    brick_architect: Optional[str] = None
    lego_pick_a_brick: Optional[str] = None
    bricklink: Optional[str] = None
    rebrickable: Optional[str] = None
    brickset: Optional[str] = None
    ldraw: Optional[str] = None


class PartCrossReferenceResponse(BaseModel):
    """API response for a part number lookup."""

    part_number: str
    brick_architect_part_number: Optional[str] = None
    alternative_part_numbers: dict[str, str] = Field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def from_alternatives(
        cls,
        part_number: str,
        alternatives: dict[str, str],
        *,
        brick_architect_part_number: Optional[str] = None,
        error: Optional[str] = None,
    ) -> "PartCrossReferenceResponse":
        """Build a response, omitting empty alternative values."""
        filtered = {key: value for key, value in alternatives.items() if value}
        resolved_ba_number = brick_architect_part_number or filtered.get("brick_architect")
        if resolved_ba_number:
            filtered["brick_architect"] = resolved_ba_number

        ordered: dict[str, str] = {}
        if "brick_architect" in filtered:
            ordered["brick_architect"] = filtered["brick_architect"]
        for key, value in filtered.items():
            if key != "brick_architect":
                ordered[key] = value

        return cls(
            part_number=part_number,
            brick_architect_part_number=resolved_ba_number,
            alternative_part_numbers=ordered,
            error=error,
        )
