"""
The Polite Scraper – FlyRank Internship Backend Track Week 5 Assignment A9
===========================================================================
Target: https://books.toscrape.com/

I will not reuse this code on another site without checking its rules and terms first.

Target classification:
  - The target (books.toscrape.com) is a sandbox/demo site specifically designed
    for web scraping practice. The header itself states "We love being scraped!"
  - robots.txt returns 404 (no robots.txt file present) — no disallow rules.
  - The site places no restrictions on scraping, but we follow polite best
    practices anyway as a matter of professional discipline.

Architecture: fetch → extract → normalize → validate → store → report
"""

import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, field_validator, HttpUrl

# ── Configuration ──────────────────────────────────────────────────────────────

BASE_URL = "https://books.toscrape.com/catalogue/"
START_URL = "https://books.toscrape.com/catalogue/page-1.html"
MAX_PAGES = 3
MIN_DELAY = 0.5  # 500 ms between real network requests
TIMEOUT = 15
USER_AGENT = "FlyRankAssignmentBot/1.0 (+https://github.com/flyrank; polite-scraper-assignment)"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# Fake URL for failure testing (Stage 5)
FAKE_URL_FOR_TESTING = "https://books.toscrape.com/catalogue/fake-book-does-not-exist_999999/index.html"

# ── Pydantic Schema ────────────────────────────────────────────────────────────

class BookRecord(BaseModel):
    title: str
    product_url: str
    price_gbp: float
    price_text: str
    availability_text: str
    rating_text: str
    description: str | None
    source_page: str
    fetched_at: str

    @field_validator("price_gbp")
    @classmethod
    def price_must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("price_gbp must be non-negative")
        return round(v, 2)

class ErrorRecord(BaseModel):
    url: str
    reason: str
    source_page: str
    attempted_at: str

class RunReport(BaseModel):
    start_time: str
    end_time: str
    duration_seconds: float
    pages_fetched: int
    cache_hits: int
    valid_records: int
    invalid_records: int
    failed_pages: list[str]


# ── Networking Helpers ──────────────────────────────────────────────────────────

class PolitFetcher:
    """Polite HTTP fetcher with caching, delay, retries, and user-agent."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.last_request_time: float = 0.0
        self.cache_hits: int = 0
        self.network_requests: int = 0

    def _wait(self) -> None:
        elapsed = time.time() - self.last_request_time
        if elapsed < MIN_DELAY and self.last_request_time > 0:
            wait_time = MIN_DELAY - elapsed
            print(f"  Waiting {wait_time:.2f}s (politeness delay)...")
            time.sleep(wait_time)

    def _cache_path(self, url: str) -> Path:
        # Catalogue pages keep a readable name (Stage 1 requirement);
        # everything else is keyed by a hash of the URL.
        m = re.match(r"https://books\.toscrape\.com/catalogue/page-(\d+)\.html", url)
        if m:
            return CACHE_DIR / f"catalogue-page-{m.group(1)}.html"
        name = hashlib.md5(url.encode()).hexdigest() + ".html"
        return CACHE_DIR / name

    def _is_cache_hit(self, cache_file: Path) -> bool:
        return cache_file.exists() and cache_file.stat().st_size > 0

    def fetch(self, url: str, label: str = "") -> str | None:
        """Fetch a URL, respecting cache and politeness rules.

        Returns HTML string or None on failure.
        """
        cache_file = self._cache_path(url)

        if self._is_cache_hit(cache_file):
            print(f"  CACHE HIT  {label or url}")
            self.cache_hits += 1
            return cache_file.read_text(encoding="utf-8")

        self._wait()
        print(f"  Fetching   {label or url}")
        self.network_requests += 1

        try:
            resp = self.session.get(url, timeout=TIMEOUT)
            self.last_request_time = time.time()
        except requests.exceptions.Timeout:
            print(f"  TIMEOUT on {label or url} — retrying once...")
            time.sleep(2)
            try:
                resp = self.session.get(url, timeout=TIMEOUT)
                self.last_request_time = time.time()
            except Exception as e:
                print(f"  FAILED     {label or url}: {e}")
                return None

        # Check status code
        if resp.status_code in (403, 404):
            print(f"  HTTP {resp.status_code}  {label or url} — not retrying")
            return None

        if resp.status_code >= 500:
            print(f"  HTTP {resp.status_code}  {label or url} — retrying once...")
            time.sleep(2)
            try:
                resp = self.session.get(url, timeout=TIMEOUT)
                self.last_request_time = time.time()
            except Exception as e:
                print(f"  FAILED     {label or url}: {e}")
                return None
            if resp.status_code >= 500:
                print(f"  HTTP {resp.status_code}  {label or url} — giving up")
                return None

        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}  {label or url} — skipping")
            return None

        # Fix encoding: the site sends UTF-8 but declares no charset, so
        # requests defaults to ISO-8859-1. Force the apparent encoding so
        # multi-byte characters like £ are decoded correctly.
        resp.encoding = resp.apparent_encoding or "utf-8"

        # Cache it
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(resp.text, encoding="utf-8")
        print(f"  CACHED     {label or url}")
        return resp.text


# ── Stage 2: Discover book URLs from catalogue pages ────────────────────────────

def discover_book_urls(fetcher: PolitFetcher) -> list[str]:
    """Parse catalogue pages 1-3 and collect unique book detail URLs."""
    all_urls: list[str] = []
    current_url = START_URL
    pages_fetched = 0

    while current_url and pages_fetched < MAX_PAGES:
        pages_fetched += 1
        print(f"\n[Stage 2] Discovering books on catalogue page {pages_fetched}...")
        print(f"  URL: {current_url}")

        html = fetcher.fetch(current_url, label=f"catalogue page {pages_fetched}")
        if html is None:
            print(f"  Failed to fetch catalogue page {pages_fetched}, stopping discovery.")
            break

        soup = BeautifulSoup(html, "html.parser")

        # Find all book links in the catalogue listing
        for article in soup.select("article.product_pod"):
            h3 = article.find("h3")
            if h3:
                a = h3.find("a")
                if a and a.get("href"):
                    relative = a["href"]
                    absolute = urljoin(current_url, relative)
                    all_urls.append(absolute)

        # Follow the site's own "next" link
        next_li = soup.select_one("li.next a")
        if next_li and next_li.get("href"):
            next_href = next_li["href"]
            if pages_fetched < MAX_PAGES:
                current_url = urljoin(current_url, next_href)
            else:
                current_url = None
        else:
            current_url = None

    # Deduplicate while preserving order
    seen = set()
    unique_urls = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    print(f"\n  catalogue_pages={pages_fetched}")
    print(f"  discovered={len(all_urls)}")
    print(f"  unique_urls={len(unique_urls)}")

    return unique_urls


# ── Stage 3: Extract raw fields from each book detail page ──────────────────────

RATING_MAP = {
    "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5
}

def extract_book_detail(html: str, url: str, source_page: str) -> dict:
    """Extract raw fields from a book detail page's HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Title
    h1 = soup.select_one("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Price text
    price_p = soup.select_one("p.price_color")
    price_text = price_p.get_text(strip=True) if price_p else ""

    # Availability text
    avail_p = soup.select_one("p.instock.availability")
    availability_text = avail_p.get_text(strip=True) if avail_p else ""

    # Rating text
    rating_p = soup.select_one("p.star-rating")
    if rating_p:
        classes = rating_p.get("class", [])
        rating_class = [c for c in classes if c != "star-rating"]
        rating_text = rating_class[0] if rating_class else ""
    else:
        rating_text = ""

    # Description
    desc_div = soup.select_one("#product_description")
    if desc_div:
        next_p = desc_div.find_next_sibling("p")
        description = next_p.get_text(strip=True) if next_p else None
    else:
        description = None

    # Fetched at
    fetched_at = datetime.now(timezone.utc).isoformat()

    return {
        "title": title,
        "product_url": url,
        "price_text": price_text,
        "availability_text": availability_text,
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": fetched_at,
    }


# ── Stage 4: Normalize and validate ─────────────────────────────────────────────

def normalize_price(price_text: str) -> float:
    """Convert '£51.77' or 'Â£51.77' to 51.77.

    books.toscrape.com sends the £ sign as the two-byte UTF-8 sequence
    \xc2\xa3 which BeautifulSoup renders as 'Â' followed by '£'. We
    strip all non-numeric prefix characters to handle this gracefully.
    """
    import re
    cleaned = re.sub(r"[^\d.]", "", price_text)
    return float(cleaned)


def normalize_and_validate(
    raw_records: list[dict],
) -> tuple[list[BookRecord], list[ErrorRecord]]:
    """Normalize raw records, validate with Pydantic, return valid + invalid."""
    valid: list[BookRecord] = []
    invalid: list[ErrorRecord] = []

    seen_urls: set[str] = set()

    for rec in raw_records:
        url = rec["product_url"]
        now_str = datetime.now(timezone.utc).isoformat()

        # Deduplication by canonical URL
        if url in seen_urls:
            invalid.append(ErrorRecord(
                url=url,
                reason=f"Duplicate URL: {url}",
                source_page=rec["source_page"],
                attempted_at=now_str,
            ))
            continue
        seen_urls.add(url)

        try:
            price_gbp = normalize_price(rec["price_text"])
        except (ValueError, TypeError) as e:
            invalid.append(ErrorRecord(
                url=url,
                reason=f"Price normalization failed: {e}",
                source_page=rec["source_page"],
                attempted_at=now_str,
            ))
            continue

        record_data = {**rec, "price_gbp": price_gbp}

        try:
            book = BookRecord(**record_data)
            valid.append(book)
        except Exception as e:
            invalid.append(ErrorRecord(
                url=url,
                reason=f"Validation failed: {e}",
                source_page=rec["source_page"],
                attempted_at=now_str,
            ))

    return valid, invalid


# ── Stage 5: Store ──────────────────────────────────────────────────────────────

def store_results(valid: list[BookRecord], invalid: list[ErrorRecord]) -> None:
    """Write output/books.json and output/errors.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Merge with existing books.json if present (idempotent – never duplicate)
    books_path = OUTPUT_DIR / "books.json"
    existing_urls: dict[str, dict] = {}
    if books_path.exists():
        existing = json.loads(books_path.read_text(encoding="utf-8"))
        for b in existing:
            existing_urls[b["product_url"]] = b

    for book in valid:
        existing_urls[book.product_url] = book.model_dump()

    books_list = list(existing_urls.values())
    books_path.write_text(json.dumps(books_list, indent=2, ensure_ascii=False), encoding="utf-8")

    # Errors: merge with existing
    errors_path = OUTPUT_DIR / "errors.json"
    existing_errors: dict[str, dict] = {}
    if errors_path.exists():
        existing_err = json.loads(errors_path.read_text(encoding="utf-8"))
        for e in existing_err:
            existing_errors[e["url"]] = e

    for err in invalid:
        existing_errors[err.url] = err.model_dump()

    errors_list = list(existing_errors.values())
    errors_path.write_text(json.dumps(errors_list, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Stage 5: Run Report ────────────────────────────────────────────────────────

def write_report(
    start_time: datetime,
    pages_fetched: int,
    cache_hits: int,
    valid_count: int,
    invalid_count: int,
    failed_pages: list[str],
) -> RunReport:
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    report = RunReport(
        start_time=start_time.isoformat(),
        end_time=end_time.isoformat(),
        duration_seconds=round(duration, 2),
        pages_fetched=pages_fetched,
        cache_hits=cache_hits,
        valid_records=valid_count,
        invalid_records=invalid_count,
        failed_pages=failed_pages,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "run-report.json"
    report_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
    print(f"\n  Report saved to {report_path}")
    return report


# ── Main Pipeline ───────────────────────────────────────────────────────────────

def main() -> None:
    start_time = datetime.now(timezone.utc)
    print("=" * 60)
    print("The Polite Scraper – Assignment A9")
    print("=" * 60)
    print(f"Target:     https://books.toscrape.com/")
    print(f"User-Agent: {USER_AGENT}")
    print(f"Delay:      {MIN_DELAY}s minimum between requests")
    print(f"Timeout:    {TIMEOUT}s")
    print(f"Max pages:  {MAX_PAGES}")
    print()

    fetcher = PolitFetcher()
    failed_pages: list[str] = []

    # ── Stage 2: Discover book URLs from catalogue pages ──
    book_urls = discover_book_urls(fetcher)
    pages_fetched = MAX_PAGES  # we always attempt 3 pages

    # ── Stage 3: Fetch & extract each book detail page ──
    raw_records: list[dict] = []

    print(f"\n[Stage 3] Extracting details for {len(book_urls)} books...")

    for i, url in enumerate(book_urls, 1):
        source_page = f"catalogue/page-{((i - 1) // 20) + 1}.html"
        print(f"  [{i}/{len(book_urls)}] {url}")

        html = fetcher.fetch(url, label=f"book {i}/{len(book_urls)}")
        if html is None:
            print(f"    SKIP (fetch failed)")
            failed_pages.append(url)
            # Handled independently: a broken page becomes an error record,
            # but does not crash the run.
            raw_records.append({
                "title": "",
                "product_url": url,
                "price_text": "",
                "availability_text": "",
                "rating_text": "",
                "description": None,
                "source_page": source_page,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
            continue

        try:
            record = extract_book_detail(html, url, source_page)
            raw_records.append(record)
        except Exception as e:
            print(f"    ERROR extracting: {e}")
            failed_pages.append(url)

    # ── Stage 5 (test): Add a deliberately fake URL to test failure handling ──
    print(f"\n[Stage 5] Testing failure handling with fake URL...")
    print(f"  URL: {FAKE_URL_FOR_TESTING}")
    fake_html = fetcher.fetch(FAKE_URL_FOR_TESTING, label="fake-test-page")
    if fake_html is None:
        print("  A fake/broken page is expected to fail. It is logged and skipped,")
        print("  and it does NOT crash or corrupt the rest of the run.")
        failed_pages.append(FAKE_URL_FOR_TESTING)
        raw_records.append({
            "title": "",
            "product_url": FAKE_URL_FOR_TESTING,
            "price_text": "",
            "availability_text": "",
            "rating_text": "",
            "description": None,
            "source_page": "test",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        try:
            fake_record = extract_book_detail(fake_html, FAKE_URL_FOR_TESTING, "test")
            raw_records.append(fake_record)
        except Exception as e:
            print(f"  Fake page extraction error (expected): {e}")
            failed_pages.append(FAKE_URL_FOR_TESTING)

    # ── Stage 4: Normalize and validate ──
    print(f"\n[Stage 4] Normalizing and validating {len(raw_records)} records...")
    valid, invalid = normalize_and_validate(raw_records)
    print(f"  valid={len(valid)}  invalid={len(invalid)}")

    # ── Stage 5: Store results ──
    print(f"\n[Stage 5] Storing results...")
    store_results(valid, invalid)

    # ── Stage 5: Write report ──
    report = write_report(
        start_time=start_time,
        pages_fetched=pages_fetched,
        cache_hits=fetcher.cache_hits,
        valid_count=len(valid),
        invalid_count=len(invalid),
        failed_pages=failed_pages,
    )

    # ── Summary ──
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Pages fetched:    {report.pages_fetched}")
    print(f"  Cache hits:       {report.cache_hits}")
    print(f"  Network requests: {fetcher.network_requests}")
    print(f"  Valid records:    {report.valid_records}")
    print(f"  Invalid records:  {report.invalid_records}")
    print(f"  Failed pages:     {len(report.failed_pages)}")
    print(f"  Duration:         {report.duration_seconds}s")
    print(f"\n  Output: {OUTPUT_DIR / 'books.json'}")
    print(f"  Report: {OUTPUT_DIR / 'run-report.json'}")


if __name__ == "__main__":
    main()
