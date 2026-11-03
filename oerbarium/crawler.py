import logging
from datetime import UTC, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .config import (
    CARPENTRY_GITHUB_ORG,
    CRAWL_TIMEOUT_SECONDS,
    GITHUB_API_BASE_URL,
    GITHUB_API_VERSION,
    GITHUB_PAGE_SIZE,
    GITHUB_TOKEN_ENV_VAR,
)
from .errors import CrawlError, InputError, RateLimitError
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
        timeout: float = CRAWL_TIMEOUT_SECONDS,
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


def parse_carpentry_repo(
    repo: dict,
    readme: str | None,
    license_text: str | None,
    release: dict | None,
) -> dict:
    """
    The metadata of one Carpentries lesson repository, from its GitHub listing
    entry plus the separately fetched README, LICENSE text and latest release.
    """
    if not repo.get("name") or not repo.get("html_url"):
        raise CrawlError("Repository entry has no name or URL.")

    # GitHub reports NOASSERTION for the Carpentries' CC-BY + MIT LICENSE.md,
    # so the raw text is kept for the parse step to read the actual license.
    license_info = repo.get("license") or {}

    return {
        "name": repo["name"],
        "description": repo.get("description"),
        "url": repo["html_url"],
        "homepage": repo.get("homepage") or None,
        "topics": repo.get("topics", []),
        "language": repo.get("language"),
        "created_at": repo.get("created_at"),
        "pushed_at": repo.get("pushed_at"),
        "archived": repo.get("archived", False),
        "fork": repo.get("fork", False),
        "license": license_info.get("name"),
        "license_spdx_id": license_info.get("spdx_id"),
        "license_text": license_text,
        "latest_release_tag": release.get("tag_name") if release else None,
        "latest_release_date": release.get("published_at") if release else None,
        "readme": readme,
    }


class CarpentryCrawler:
    """Lists the repositories of a Carpentries GitHub org and turns each into a metadata record."""

    _RAW = "application/vnd.github.raw+json"

    def __init__(
        self,
        org: str = CARPENTRY_GITHUB_ORG,
        include_archived: bool = False,
        token: str | None = None,
        strict: bool = False,
        reporter: ProgressReporter | None = None,
        timeout: float = CRAWL_TIMEOUT_SECONDS,
    ):
        self._org = org
        self._include_archived = include_archived
        self._has_token = bool(token)
        self._strict = strict
        self._reporter = reporter or NullProgressReporter()
        self._timeout = timeout
        self.skipped = 0
        self.records: list[dict] = []
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            }
        )
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def crawl(self) -> list[dict]:
        """
        Crawl every repository of the org, skipping the ones that fail unless
        `strict` is set. An exhausted rate limit always aborts the run.

        `records` holds every repository crawled so far, also after a run aborted.
        """
        if not self._has_token:
            logger.warning(
                "No GitHub token set: the API allows only 60 requests per hour, "
                "too few for a full crawl. Set %s.",
                GITHUB_TOKEN_ENV_VAR,
            )

        repos = self._list_repos()
        self.records = []
        self.skipped = 0
        for number, repo in enumerate(repos, start=1):
            logger.info("Crawling %s/%s: %s", number, len(repos), repo.get("full_name"))
            self._reporter.report(number, len(repos))
            try:
                self.records.append(self._fetch(repo))
            except RateLimitError:
                raise
            except CrawlError as exc:
                if self._strict:
                    raise
                self.skipped += 1
                logger.warning("Skipping %s: %s", repo.get("full_name"), exc)
        return self.records

    def _list_repos(self) -> list[dict]:
        """The org's public repositories, without archived ones unless asked for."""
        url: str | None = (
            f"{GITHUB_API_BASE_URL}/orgs/{self._org}/repos"
            f"?per_page={GITHUB_PAGE_SIZE}&type=public"
        )
        repos: list[dict] = []
        while url:
            response = self._get(url)
            if response is None:
                raise CrawlError(f"GitHub organisation '{self._org}' not found.")
            repos += response.json()
            url = response.links.get("next", {}).get("url")

        if self._include_archived:
            return repos
        active = [repo for repo in repos if not repo.get("archived")]
        logger.info(
            "Found %s repositories, skipping %s archived",
            len(repos),
            len(repos) - len(active),
        )
        return active

    def _fetch(self, repo: dict) -> dict:
        """The metadata of a single repository: three API calls."""
        base = f"{GITHUB_API_BASE_URL}/repos/{repo['full_name']}"
        readme = self._get(f"{base}/readme", raw=True)
        license_file = self._get(f"{base}/license", raw=True)
        release = self._get(f"{base}/releases/latest")
        return parse_carpentry_repo(
            repo,
            readme=readme.text if readme else None,
            license_text=license_file.text if license_file else None,
            release=release.json() if release else None,
        )

    def _get(self, url: str, raw: bool = False) -> requests.Response | None:
        """
        A GitHub API response, or None when the resource does not exist
        (no README, no LICENSE, no release).
        """
        headers = {"Accept": self._RAW} if raw else None
        try:
            response = self._session.get(url, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            raise CrawlError(f"{url} could not be fetched: {exc}") from exc

        if response.status_code == 404:
            return None
        if (
            response.status_code in (403, 429)
            and response.headers.get("X-RateLimit-Remaining") == "0"
        ):
            raise RateLimitError(self._rate_limit_message(response))
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise CrawlError(f"{url} could not be fetched: {exc}") from exc
        return response

    def _rate_limit_message(self, response: requests.Response) -> str:
        message = "GitHub API rate limit exhausted"
        if reset := response.headers.get("X-RateLimit-Reset"):
            at = datetime.fromtimestamp(int(reset), tz=UTC)
            message += f"; it resets at {at:%Y-%m-%d %H:%M} UTC"
        if not self._has_token:
            message += f". Set {GITHUB_TOKEN_ENV_VAR} or pass --github-token to raise the limit"
        return message + "."
