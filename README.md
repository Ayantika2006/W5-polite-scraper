# The Polite Scraper

FlyRank Internship — Backend Track — Week 5 — Assignment A9

A polite, cache-friendly web scraper for [**books.toscrape.com**](https://books.toscrape.com/). The final implementation discovers the first 60 books from the first three catalogue pages, extracts their detail data, validates it with Pydantic, and stores clean JSON output plus a run report.

> **I will not reuse this code on another site without checking its rules and terms first.**

---

## Target classification

- `books.toscrape.com` is a public **sandbox / demo** site built explicitly for web scraping practice — its header reads *"We love being scraped!"* and every page warns that prices/ratings are randomly assigned demo data with no real meaning.
- **robots.txt** — checked: `https://books.toscrape.com/robots.txt` returns **HTTP 404**, meaning the site publishes **no robots restrictions**.
- Low risk: no personal data, no accounts, no paywalled content. Still, we scrape politely and conservatively.
