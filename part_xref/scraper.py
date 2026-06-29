"""Scraper for Brick Architect part pages."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from part_xref.config import (
    BRICK_ARCHITECT_BASE_URL,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

# Maps Brick Architect label text to API response keys.
# Add new sources here as Brick Architect expands their External Links section.
SOURCE_LABEL_MAP: dict[str, str] = {
    "lego pick a brick": "lego_pick_a_brick",
    "bricklink": "bricklink",
    "rebrickable": "rebrickable",
    "brickset": "brickset",
    "ldraw": "ldraw",
}

NOT_FOUND_MARKERS = (
    "not found",
    "part name not found",
    "part not found",
)


@dataclass
class ScrapeResult:
    """Result of scraping a Brick Architect part page."""

    part_number: str
    brick_architect_part_number: Optional[str] = None
    alternatives: dict[str, str] = field(default_factory=dict)
    found: bool = True
    error: Optional[str] = None


class BrickArchitectScraper:
    """Fetches and parses Brick Architect part pages."""

    def __init__(
        self,
        *,
        base_url: str = BRICK_ARCHITECT_BASE_URL,
        timeout: float = REQUEST_TIMEOUT,
        user_agent: str = USER_AGENT,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def fetch_part(self, part_number: str) -> ScrapeResult:
        """Retrieve alternative part numbers for a LEGO part."""
        normalized = part_number.strip()
        if not normalized:
            return ScrapeResult(
                part_number=part_number,
                found=False,
                error="Invalid part number.",
            )

        url = f"{self.base_url}/{normalized}"
        logger.info("Scraping Brick Architect page", extra={"url": url})

        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.Timeout:
            logger.exception("Brick Architect request timed out", extra={"url": url})
            return ScrapeResult(
                part_number=normalized,
                found=False,
                error="Request timed out while contacting Brick Architect.",
            )
        except requests.RequestException:
            logger.exception("Brick Architect request failed", extra={"url": url})
            return ScrapeResult(
                part_number=normalized,
                found=False,
                error="Network error while contacting Brick Architect.",
            )

        if response.status_code == 404:
            return self._parse_not_found_page(normalized, response.text, response.url)

        if response.status_code != 200:
            logger.warning(
                "Unexpected HTTP status from Brick Architect",
                extra={"url": url, "status_code": response.status_code},
            )
            return ScrapeResult(
                part_number=normalized,
                found=False,
                error=f"Brick Architect returned HTTP {response.status_code}.",
            )

        return self._parse_part_page(normalized, response.text, response.url)

    def _parse_not_found_page(
        self, part_number: str, html: str, final_url: str
    ) -> ScrapeResult:
        """Handle Brick Architect 404 pages that still expose external links."""
        soup = BeautifulSoup(html, "lxml")
        if self._page_indicates_not_found(soup):
            logger.info("Part not found on Brick Architect", extra={"part_number": part_number})
            return ScrapeResult(
                part_number=part_number,
                found=False,
                error="Part number not found.",
            )
        return self._parse_part_page(part_number, html, final_url)

    def _parse_part_page(
        self, part_number: str, html: str, final_url: str
    ) -> ScrapeResult:
        soup = BeautifulSoup(html, "lxml")
        if self._page_indicates_not_found(soup):
            return ScrapeResult(
                part_number=part_number,
                found=False,
                error="Part number not found.",
            )

        brick_architect_number = self._extract_brick_architect_part_number(
            soup, final_url
        )
        alternatives = self._extract_external_links(soup, part_number)
        if brick_architect_number:
            alternatives["brick_architect"] = brick_architect_number

        return ScrapeResult(
            part_number=part_number,
            brick_architect_part_number=brick_architect_number,
            alternatives=alternatives,
            found=True,
        )

    def _extract_brick_architect_part_number(
        self, soup: BeautifulSoup, final_url: str
    ) -> Optional[str]:
        """Extract Brick Architect's canonical part number for the resolved page."""
        from_url = self._part_number_from_url(final_url)
        if from_url:
            return from_url

        heading = soup.find("h1")
        if heading is not None:
            match = re.search(
                r"\(Part\s+([^)]+)\)",
                heading.get_text(" ", strip=True),
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(1).strip()

        if soup.title and soup.title.string:
            match = re.match(r"^(\S+)\s+-", soup.title.string.strip())
            if match:
                return match.group(1).strip()

        return None

    def _part_number_from_url(self, url: str) -> Optional[str]:
        path = urlparse(url).path.rstrip("/")
        if not path.startswith("/parts/"):
            return None
        part_slug = path.rsplit("/", maxsplit=1)[-1]
        if part_slug and part_slug not in {"search", "category-1"}:
            return part_slug
        return None

    def _page_indicates_not_found(self, soup: BeautifulSoup) -> bool:
        title = (soup.title.string or "").lower() if soup.title else ""
        if "not found" in title:
            return True

        heading = soup.find("h1")
        if heading and "not found" in heading.get_text(" ", strip=True).lower():
            return True

        return False

    def _extract_external_links(
        self, soup: BeautifulSoup, part_number: str
    ) -> dict[str, str]:
        """Parse the External Links section into source -> part number mappings."""
        section = self._find_external_links_section(soup)
        if section is None:
            logger.warning(
                "External Links section missing",
                extra={"part_number": part_number},
            )
            return {}

        alternatives: dict[str, str] = {}
        for detail in section.select("div.part_detail"):
            label = detail.select_one("div.part_detail_label")
            if label is None:
                continue

            source_key = self._normalize_source_label(label.get_text(" ", strip=True))
            if source_key is None:
                continue

            part_nums = self._extract_part_numbers_from_detail(detail, part_number)
            if not part_nums:
                continue

            preferred = self._pick_preferred_part_number(part_nums, part_number)
            if source_key == "ldraw" and not preferred.endswith(".dat"):
                preferred = f"{preferred}.dat"

            alternatives[source_key] = preferred

        return alternatives

    def _find_external_links_section(self, soup: BeautifulSoup) -> Optional[Tag]:
        heading = soup.find(
            lambda tag: tag.name == "h2"
            and "external links" in tag.get_text(" ", strip=True).lower()
        )
        if heading is None:
            return None

        container = heading.find_parent("div", class_="partoverview")
        if container is not None:
            return container

        # Fallback: walk forward siblings until we leave the details block.
        current: Optional[Tag] = heading
        collected: list[Tag] = []
        while current is not None:
            collected.append(current)
            current = current.find_next_sibling()
            if current and current.name == "h2":
                break

        wrapper = soup.new_tag("div")
        for node in collected:
            wrapper.append(node.extract() if node.parent else node)
        return wrapper

    def _normalize_source_label(self, label: str) -> Optional[str]:
        cleaned = label.strip().rstrip(":").lower()
        return SOURCE_LABEL_MAP.get(cleaned)

    def _extract_part_numbers_from_detail(
        self, detail: Tag, requested_part_number: str
    ) -> list[str]:
        numbers: list[str] = []
        for entry in detail.select("div.part_detail_externalpart"):
            note = entry.select_one("span.part_note")
            if note and self._note_indicates_missing(note.get_text(" ", strip=True)):
                continue

            part_num_el = entry.select_one("span.part_num")
            if part_num_el is not None:
                value = part_num_el.get_text(strip=True)
                if value:
                    numbers.append(value)
                    continue

            link = entry.find("a", href=True)
            if link is not None:
                extracted = self._extract_part_number_from_href(
                    link["href"], requested_part_number
                )
                if extracted:
                    numbers.append(extracted)

        return numbers

    def _note_indicates_missing(self, note: str) -> bool:
        lowered = note.lower()
        return any(marker in lowered for marker in NOT_FOUND_MARKERS)

    def _extract_part_number_from_href(
        self, href: str, requested_part_number: str
    ) -> Optional[str]:
        decoded = unquote(href)

        patterns = (
            r"[?&]P=([^&]+)",
            r"/parts/([^/?#]+)",
            r"design-([^/?#]+)",
            r"tableSearch=([^&]+)\.dat",
            r"query=([^&]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, decoded, flags=re.IGNORECASE)
            if match:
                return match.group(1)

        path = urlparse(decoded).path.rstrip("/").split("/")[-1]
        if path and path != requested_part_number:
            return path
        return requested_part_number

    def _pick_preferred_part_number(
        self, part_numbers: list[str], requested_part_number: str
    ) -> str:
        requested_lower = requested_part_number.lower()
        for candidate in part_numbers:
            if candidate.lower() == requested_lower:
                return candidate
        return part_numbers[0]
