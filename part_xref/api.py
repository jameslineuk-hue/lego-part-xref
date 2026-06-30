"""FastAPI routes for the part cross-reference service."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from part_xref.cache import PartCrossReferenceCache
from part_xref.config import TEMPLATES_DIR
from part_xref.import_csv import parse_part_numbers_csv
from part_xref.models import (
    CsvImportResult,
    PartCrossReferenceResponse,
    SaveXrefResponse,
    XrefCountResponse,
)
from part_xref.scraper import BrickArchitectScraper
from part_xref.xref_db import PartXrefStore

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

scraper = BrickArchitectScraper()
cache = PartCrossReferenceCache()
xref_store = PartXrefStore()


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


def _save_lookup_result(response: PartCrossReferenceResponse) -> SaveXrefResponse:
    """Persist a lookup result if it is valid and not already stored."""
    part_number = response.part_number.strip()
    if not part_number:
        return SaveXrefResponse(
            part_number=response.part_number,
            saved=False,
            message="Invalid part number.",
        )

    if response.error and not response.alternative_part_numbers:
        return SaveXrefResponse(
            part_number=part_number,
            saved=False,
            message=response.error or "Part could not be resolved.",
        )

    if xref_store.exists(part_number):
        return SaveXrefResponse(
            part_number=part_number,
            saved=False,
            message="Xref entry already exists.",
        )

    inserted = xref_store.insert(
        part_number,
        brick_architect_part_number=response.brick_architect_part_number,
        alternative_part_numbers=response.alternative_part_numbers,
    )
    if inserted:
        return SaveXrefResponse(
            part_number=part_number,
            saved=True,
            message="Xref entry saved.",
        )

    return SaveXrefResponse(
        part_number=part_number,
        saved=False,
        message="Xref entry already exists.",
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"xref_count": xref_store.count()},
    )


@router.get(
    "/api/lego/part-xrefs/count",
    response_model=XrefCountResponse,
    summary="Return the number of stored part cross-reference entries",
)
async def get_part_xref_count() -> XrefCountResponse:
    return XrefCountResponse(count=xref_store.count())


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


@router.post(
    "/api/lego/part-xrefs/import",
    response_model=CsvImportResult,
    summary="Import part numbers from CSV and generate xref entries",
)
async def import_part_xrefs_csv(file: UploadFile) -> CsvImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="A .csv file is required.")

    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.") from exc

    part_numbers = parse_part_numbers_csv(content)
    if not part_numbers:
        raise HTTPException(
            status_code=400,
            detail="No part numbers found in CSV.",
        )

    imported = 0
    skipped_existing = 0
    not_found: list[str] = []
    failed: list[str] = []

    for part_number in part_numbers:
        if xref_store.exists(part_number):
            skipped_existing += 1
            continue

        response = lookup_part(part_number)

        if response.error and not response.alternative_part_numbers:
            if response.error == "Part number not found.":
                not_found.append(part_number)
            else:
                failed.append(f"{part_number} ({response.error})")
            continue

        if xref_store.insert(
            part_number,
            brick_architect_part_number=response.brick_architect_part_number,
            alternative_part_numbers=response.alternative_part_numbers,
        ):
            imported += 1
        else:
            skipped_existing += 1

    logger.info(
        "CSV import complete",
        extra={
            "total": len(part_numbers),
            "imported": imported,
            "skipped_existing": skipped_existing,
            "not_found": len(not_found),
            "failed": len(failed),
        },
    )

    return CsvImportResult(
        total=len(part_numbers),
        imported=imported,
        skipped_existing=skipped_existing,
        not_found=not_found,
        failed=failed,
    )


@router.post(
    "/api/lego/part-xrefs/{part_number}",
    response_model=SaveXrefResponse,
    summary="Save a part cross-reference lookup result",
)
async def save_part_xref(part_number: str) -> SaveXrefResponse:
    logger.info("Save xref request", extra={"part_number": part_number})
    response = lookup_part(part_number)
    return _save_lookup_result(response)
