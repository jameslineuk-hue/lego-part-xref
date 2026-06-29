"""FastAPI routes for the part cross-reference service."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from part_xref.cache import PartCrossReferenceCache
from part_xref.config import TEMPLATES_DIR
from part_xref.models import PartCrossReferenceResponse
from part_xref.scraper import BrickArchitectScraper

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

scraper = BrickArchitectScraper()
cache = PartCrossReferenceCache()


def lookup_part(part_number: str) -> PartCrossReferenceResponse:
    """Resolve a part number via cache and Brick Architect."""
    normalized = part_number.strip()
    if not normalized:
        return PartCrossReferenceResponse(
            part_number=part_number,
            error="Invalid part number.",
        )

    cached = cache.get(normalized)
    if cached is not None:
        return _to_response(cached)

    result = scraper.fetch_part(normalized)
    cache.set(result)
    return _to_response(result)


def _to_response(result) -> PartCrossReferenceResponse:
    return PartCrossReferenceResponse.from_alternatives(
        part_number=result.part_number,
        alternatives=result.alternatives,
        brick_architect_part_number=result.brick_architect_part_number,
        error=result.error,
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@router.get(
    "/api/lego/part-number/{part_number}",
    response_model=PartCrossReferenceResponse,
    summary="Look up alternative LEGO part numbers",
)
async def get_part_cross_reference(part_number: str) -> PartCrossReferenceResponse:
    logger.info("Incoming request", extra={"part_number": part_number})
    response = lookup_part(part_number)

    if response.error == "Invalid part number.":
        raise HTTPException(status_code=400, detail=response.model_dump())

    if response.error and not response.alternative_part_numbers:
        # Known missing parts and upstream failures return 200 with an error field.
        return response

    return response
