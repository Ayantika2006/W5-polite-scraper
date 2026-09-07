# The Polite Scraper

FlyRank Internship — Backend Track — Week 5 — Assignment A9

A polite, cache-friendly web scraper for [**books.toscrape.com**](https://books.toscrape.com/). The final implementation discovers the first 60 books from the first three catalogue pages, extracts their detail data, validates it with Pydantic, and stores clean JSON output plus a run report.

> **I will not reuse this code on another site without checking its rules and terms first.**

---

## Target classification

- `books.toscrape.com` is a public **sandbox / demo** site built explicitly for web scraping practice — its header reads *"We love being scraped!"* and every page warns that prices/ratings are randomly assigned demo data with no real meaning.
- **robots.txt** — checked: `https://books.toscrape.com/robots.txt` returns **HTTP 404**, meaning the site publishes **no robots restrictions**.
- Low risk: no personal data, no accounts, no paywalled content. Still, we scrape politely and conservatively.

---

## Fetch and cache HTML (Stage 1)

- Catalogue page 1 is fetched and saved as `cache/catalogue-page-1.html`.
- The **first run** performs a real network request; the **second run** reads from cache and prints `CACHE HIT` — the server is not hit again.
- Every page fetched (catalogue + book details) is cached under `cache/`, keyed by URL.

### Politeness rules

- **User-Agent** — honest and identifying: `FlyRankAssignmentBot/1.0 (+...; polite-scraper-assignment)`. No spoofing.
- **Timeout** — every request has a 15 s timeout.
- **HTTP status checks** — status codes are inspected on every response.
- **Delay** — at least **500 ms** between real network requests.
- **Cache** — all downloaded HTML is reused on reruns so development never hammers the server.
- **Never retry 403/404** — treated as permanent, skipped immediately.
- **Retry once** on timeout or 5xx, after a short wait, then give up.
- **No hammering** — a cold run makes ~64 requests (0.5 s apart); every rerun is served from `cache/`.

---

## Discover three catalogue pages (Stage 2)

- Book URLs are **discovered**, never hardcoded.
- The scraper parses `page-1.html`, then follows the site's own **next** link, stopping after page 3.
- Relative URLs are resolved to absolute URLs with `urllib.parse.urljoin`, then deduplicated.
- Expected output:

```
catalogue_pages=3
discovered=60
unique_urls=60
```

---

## Extract book details (Stage 3)

Each book detail page is parsed with BeautifulSoup and the following raw fields are extracted:

| Field | Notes |
|---|---|
| `title` | Book title |
| `product_url` | Canonical absolute URL — used as identity / dedup key |
| `price_text` | Raw price text as scraped, e.g. `"£51.77"` |
| `availability_text` | e.g. `"In stock (22 available)"` |
| `rating_text` | e.g. `"Three"`, `"Five"` |
| `description` | `null` when the page has no description — never invented |
| `source_page` | Which catalogue page the book was discovered on |
| `fetched_at` | ISO-8601 timestamp of when the detail page was fetched |

### Architecture

```
fetch → extract → normalize → validate → store → report
```

| Stage | Responsibility |
|---|---|
| **fetch** | Polite HTTP client with caching, UA, timeout, delay, retry rules |
| **extract** | Parse catalogue pages and book detail pages with BeautifulSoup |
| **normalize** | Convert `price_text` `"£51.77"` → numeric `price_gbp` = `51.77` |
| **validate** | Pydantic `BookRecord` schema — rejects bad/invalid records |
| **store** | `output/books.json` (valid) and `output/errors.json` (invalid + reason) |
| **report** | `output/run-report.json` — timings, counts, cache hits, failures |

---

## Validate normalized records (Stage 4)

- `price_text` such as `"£51.77"` is converted to numeric `price_gbp = 51.77`; the raw `price_text` is kept alongside.
- The canonical absolute `product_url` is used as the record identity.
- Every record is validated against the Pydantic `BookRecord` schema.
- **Valid** records → `output/books.json`.
- **Invalid** records → `output/errors.json` with the reason.
- **Idempotency** — `output/books.json` is keyed by `product_url`. Running twice still results in exactly **60 records, never 120**.

---

## Survive failures, report the run (Stage 5)

- Each book detail page is processed **independently** — one broken page cannot crash the whole run.
- A deliberately **fake URL** is injected during every run (`.../fake-book-does-not-exist_999999/index.html`). It returns **404** (never retried), is **logged and skipped**, and lands in `output/errors.json` with its reason — the 60 real records survive untouched.
- `output/run-report.json` captures the run: start time, duration, pages fetched, cache hits, valid records, invalid records, and failed pages.
