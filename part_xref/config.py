"""Configuration for the LEGO part number cross-reference API."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project paths
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
DEFAULT_CACHE_DB = BASE_DIR / "data" / "part_xref_cache.db"

# Server
DEFAULT_PORT = 8035
MIN_PORT = 8030
MAX_PORT = 8039


def get_port() -> int:
    """Return the configured server port, clamped to the allowed range."""
    raw = os.environ.get("PART_XREF_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw)
    except ValueError:
        port = DEFAULT_PORT
    return max(MIN_PORT, min(MAX_PORT, port))


# Brick Architect scraping
BRICK_ARCHITECT_BASE_URL = os.environ.get(
    "BRICK_ARCHITECT_BASE_URL", "https://brickarchitect.com/parts"
)
REQUEST_TIMEOUT = float(os.environ.get("PART_XREF_REQUEST_TIMEOUT", "15"))
USER_AGENT = os.environ.get(
    "PART_XREF_USER_AGENT",
    "LegoHub-PartXRef/1.0 (+https://github.com/legohub; educational use)",
)

# Caching
CACHE_ENABLED = os.environ.get("PART_XREF_CACHE_ENABLED", "1").lower() in {
    "1",
    "true",
    "yes",
}
CACHE_DB_PATH = Path(os.environ.get("PART_XREF_CACHE_DB", str(DEFAULT_CACHE_DB)))
CACHE_TTL_SECONDS = int(os.environ.get("PART_XREF_CACHE_TTL", str(60 * 60 * 24)))

# PostgreSQL (LegoHub persistent xref storage)
POSTGRES_HOST = os.environ.get(
    "POSTGRES_HOST", "andrews-mac-mini.coywolf-banded.ts.net"
)
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.environ.get("POSTGRES_DB", "legohub_mini")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "Birmingham.96")

# Logging
LOG_LEVEL = os.environ.get("PART_XREF_LOG_LEVEL", "INFO").upper()
