import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .errors import CrawlError, InputError
from .service import NullProgressReporter, ProgressReporter

logger = logging.getLogger(__name__)


def read_url_list(path: Path) -> list[str]:
    """
    The URLs to crawl, one per list item.
    """
    readers = {".txt": _read_plain_urls}
    reader = readers.get(path.suffix.lower())
    if reader is None:
        raise InputError(
            f"Unsupported input '{path.suffix}'. Use one of: {', '.join(readers)}."
        )

    urls = reader(path.read_text(encoding="utf-8"))
    if not urls:
        raise InputError(f"{path} contains no URLs.")
    return urls


def _read_plain_urls(text: str) -> list[str]:
    """One URL per line."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_dariah_resource(soup: BeautifulSoup) -> dict:
    """
    The metadata of one DARIAH-Campus resource page.
    """
    main = soup.find(id="main-content")
    if main is None:
        raise CrawlError("Page has no #main-content element.")

    heading = main.find("h1")
    if heading is None:
        raise CrawlError("Page has no title.")

    aside = main.find("aside") or main

    def label_siblings(label):
        el = aside.find(
            lambda t: t.name in ("dt", "div", "h2") and t.get_text(strip=True) == label
        )
        return el.find_next_siblings() if el else []

    def field(label):
        sibs = label_siblings(label)
        return " ".join(s.get_text(strip=True) for s in sibs) or None

    def authors():
        out = []
        for s in label_siblings("Authors"):
            out += [span.get_text(strip=True) for span in s.select("li span")]
        return out

    def topics():
        out = []
        for s in label_siblings("Topics"):
            out += [a.get_text(strip=True) for a in s.select("li a")]
        return out

    prose = main.find("div", class_="prose")

    return {
        "title": heading.get_text(strip=True),
        "authors": authors(),
        "topics": topics(),
        "domain": field("Domain"),
        "language": field("Language"),
        "published": field("Published to DARIAH-Campus"),
        "license": field("License"),
        "sources": field("Sources"),
        "citation": field("Cite as"),
        "description": prose.get_text("\n", strip=True) if prose else None,
    }


class DariahCrawler:
    """Fetches DARIAH-Campus resource pages and turns them into metadata records."""

    def __init__(
        self,
        strict: bool = False,
        reporter: ProgressReporter | None = None,
        timeout: float = 30.0,
    ):
        self._strict = strict
        self._reporter = reporter or NullProgressReporter()
        self._timeout = timeout

    def crawl(self, urls: list[str]) -> list[dict]:
        """
        Crawl every URL, skipping the ones that fail unless `strict` is set.
        """
        records: list[dict] = []
        for number, url in enumerate(urls, start=1):
            logger.info("Crawling %s/%s: %s", number, len(urls), url)
            self._reporter.report(number, len(urls))
            try:
                records.append(self._fetch(url))
            except CrawlError as exc:
                if self._strict:
                    raise
                logger.warning("Skipping %s: %s", url, exc)
        return records

    def _fetch(self, url: str) -> dict:
        """The metadata of a single resource page."""
        try:
            response = requests.get(url, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CrawlError(f"{url} could not be fetched: {exc}") from exc
        return parse_dariah_resource(BeautifulSoup(response.text, "html.parser"))
