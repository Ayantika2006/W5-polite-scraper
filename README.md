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
