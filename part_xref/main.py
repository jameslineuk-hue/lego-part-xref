"""Application entry point for the part cross-reference API."""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from part_xref.api import router
from part_xref.config import LOG_LEVEL

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=LOG_FORMAT,
        stream=sys.stdout,
    )


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="LEGO Part Number Cross-Reference API",
        description=(
            "Returns equivalent LEGO part numbers across major LEGO-related "
            "websites using Brick Architect as the authoritative source."
        ),
        version="1.0.0",
    )
    app.include_router(router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logging.getLogger(__name__).exception(
            "Unhandled exception",
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={
                "part_number": "",
                "alternative_part_numbers": {},
                "error": "An unexpected server error occurred.",
            },
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    from part_xref.config import get_port

    port = get_port()
    logging.getLogger(__name__).info("Starting part cross-reference API on port %s", port)
    uvicorn.run(
        "part_xref.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
