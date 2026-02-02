# Congress Signal

> **Real-time legislative intelligence for businesses.** Automated crawling of [GovInfo.gov](https://www.govinfo.gov), AI-powered extraction, and personalized email digests.

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://spontaneous-truffle-3ff463.netlify.app/)

<!-- 
  To add the demo video:
  1. Open any GitHub issue in this repo
  2. Drag congress_signal_dem.mp4 into the comment box
  3. Copy the generated URL and replace VIDEO_URL below
-->

https://github.com/user-attachments/assets/8d20f4ce-ee77-4f2d-81a4-928a777e4319

## What It Does

- **Crawls** daily federal documents (bills, regulations, executive orders)
- **Extracts** company mentions, sector impacts, and regulatory changes using AI
- **Delivers** personalized email digests filtered by your company watchlist and interests

<p align="center">
  <img width="600" alt="Dashboard" src="https://github.com/user-attachments/assets/1f5c9e12-866d-4c31-829a-4855a1cdfd04" />
</p>

<p align="center">
  <img width="400" alt="Email Digest" src="https://github.com/user-attachments/assets/b8ffd5c5-64b1-40dc-853c-1b7ccfdf034f" />
  <img width="400" alt="Extraction Details" src="https://github.com/user-attachments/assets/eb002e0d-c572-4eb5-aa3a-ea6193c6f7e2" />
</p>

## Tech Stack

| Component | Technology |
|-----------|------------|
| Crawler | Python + Firecrawl |
| Database | Supabase (Postgres) |
| Edge Functions | Deno/TypeScript |
| Emails | Resend |
| Deployment | Fly.io |

---

## Quick Start

```bash
# Install dependencies
uv sync

# Set environment variables
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_KEY=your-service-role-key

# Apply database migrations
supabase db push
```

## Usage

### Crawl Documents

```bash
# Yesterday's documents
uv run python -m crawler.govinfo --yesterday

# Specific date
uv run python -m crawler.govinfo --date 2026-01-30

# Date range
uv run python -m crawler.govinfo --start-date 2026-01-24 --end-date 2026-01-31

# Export to JSON
uv run python -m crawler.govinfo --export docs.json --date 2026-01-30
```

### Sync to Supabase

```bash
# Crawl and sync in one command
uv run python -m supabase_sync.sync --date 2026-01-30
uv run python -m supabase_sync.sync --yesterday

# Sync existing local data only
uv run python -m supabase_sync.sync --sync-only
```

---

## Project Structure

```
├── crawler/           # GovInfo document crawler
├── scripts/           # Data processing & email scripts
├── server/            # Flask API server
├── supabase/
│   ├── functions/     # Edge functions (embeddings, onboarding, search)
│   └── migrations/    # Database schema
└── supabase_sync/     # DB sync utilities
```

## Database Schema

| Column | Type | Description |
|--------|------|-------------|
| `package_id` | TEXT | Unique document ID |
| `granule_id` | TEXT | Sub-document ID |
| `title` | TEXT | Document title |
| `doc_class` | TEXT | Collection (FR, BILLS, etc.) |
| `publish_date` | DATE | Publication date |
| `pdf_url` | TEXT | Direct PDF link |
| `html_url` | TEXT | Direct HTML link |
| `details_url` | TEXT | GovInfo details page |
| `summary` | TEXT | Document excerpt |

---

## License

MIT
