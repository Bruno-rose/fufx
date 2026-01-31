# fufx - GovInfo Document Crawler

Daily crawler for govinfo.gov with Supabase sync.

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

