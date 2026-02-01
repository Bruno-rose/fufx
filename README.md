# Congress Signal

Daily crawler for [govinfo.gov](https://www.govinfo.gov/app/search/%7B%22query%22%3A%22publishdate%3Arange(2026-01-30%2C2026-01-31)%22%2C%22offset%22%3A0%2C%22facets%22%3A%7B%7D%2C%22filterOrder%22%3A%5B%5D%2C%22facetToExpand%22%3A%22companiesnav%22%7D) with Supabase sync. Powered by Firecrawl, Supabase, an Resend.


see our website: https://spontaneous-truffle-3ff463.netlify.app/

<img width="3394" height="1948" alt="image" src="https://github.com/user-attachments/assets/1f5c9e12-866d-4c31-829a-4855a1cdfd04" />

Email business digest based on company filters and interests

<img width="440" height="485" alt="image" src="https://github.com/user-attachments/assets/b8ffd5c5-64b1-40dc-853c-1b7ccfdf034f" />

<img width="2148" height="1626" alt="image" src="https://github.com/user-attachments/assets/eb002e0d-c572-4eb5-aa3a-ea6193c6f7e2" />







## Setup

```bash
uv sync
```

## Crawl Documents

```bash
# Crawl specific date
uv run python -m crawler.govinfo --date 2026-01-30

# Crawl yesterday
uv run python -m crawler.govinfo --yesterday

# Crawl date range
uv run python -m crawler.govinfo --start-date 2026-01-24 --end-date 2026-01-31

# Export to JSON
uv run python -m crawler.govinfo --export docs.json --date 2026-01-30
```

## Sync to Supabase

1. Apply migration:
```bash
# Using Supabase CLI
supabase db push

# Or copy SQL from supabase/migrations/ to Supabase Dashboard
```

2. Set environment variables:
```bash
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_KEY=your-service-role-key
```

3. Sync:
```bash
# Crawl and sync
uv run python -m supabase.sync --date 2026-01-30
uv run python -m supabase.sync --yesterday

# Sync existing SQLite data
uv run python -m supabase.sync --sync-only
```

## Project Structure

```
fufx/
├── pyproject.toml      # Dependencies
├── crawler/            # GovInfo crawler
│   └── govinfo.py
├── supabase/           # Supabase integration
│   ├── migrations/     # SQL migrations
│   └── sync.py         # Sync script
├── data/               # SQLite database (gitignored)
└── playground/         # Experiments
```

## Data Schema

| Column | Type | Description |
|--------|------|-------------|
| package_id | TEXT | Unique document package ID |
| granule_id | TEXT | Sub-document ID (optional) |
| title | TEXT | Document title |
| doc_class | TEXT | Collection code (FR, BILLS, etc.) |
| publish_date | DATE | Publication date |
| pdf_url | TEXT | Direct PDF link |
| html_url | TEXT | Direct HTML link |
| details_url | TEXT | GovInfo details page |
| summary | TEXT | Document excerpt |

