"""
Sync crawled documents to Supabase.

Usage:
    uv run python -m supabase.sync --date 2026-01-30
    uv run python -m supabase.sync --yesterday
    uv run python -m supabase.sync --sync-only
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import logging

from supabase import create_client, Client
from dotenv import load_dotenv

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from crawler.govinfo import crawl_day, init_db, DEFAULT_DB_PATH

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_supabase_client() -> Client:
    """Get Supabase client from environment variables."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables required")

    return create_client(url, key)


def sync_to_supabase(
    supabase: Client,
    docs: list[dict],
    batch_size: int = 100,
) -> int:
    """Upload documents to Supabase using upsert."""
    total = 0

    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]

        records = [
            {
                "package_id": doc["package_id"],
                "granule_id": doc["granule_id"],
                "title": doc["title"],
                "doc_class": doc["doc_class"],
                "publish_date": doc["publish_date"],
                "metadata": doc["metadata"],
                "pdf_url": doc["pdf_url"],
                "html_url": doc["html_url"],
                "details_url": doc["details_url"],
                "summary": doc["summary"],
                "crawled_at": doc["crawled_at"],
            }
            for doc in batch
        ]

        supabase.table("documents").upsert(
            records, on_conflict="package_id,granule_id"
        ).execute()

        total += len(batch)
        logger.info(f"Synced {total}/{len(docs)} documents")

    return total


def sync_from_sqlite(
    supabase: Client,
    db_path: Path,
    date: str | None = None,
) -> int:
    """Sync documents from SQLite to Supabase."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if date:
        rows = conn.execute(
            "SELECT * FROM documents WHERE publish_date = ?", (date,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM documents").fetchall()

    docs = [dict(row) for row in rows]
    conn.close()

    if not docs:
        logger.info("No documents to sync")
        return 0

    logger.info(f"Syncing {len(docs)} documents to Supabase...")
    return sync_to_supabase(supabase, docs)


def crawl_and_sync(
    supabase: Client,
    date: str,
    db_path: Path | None = None,
) -> int:
    """Crawl a date and sync directly to Supabase."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    # Crawl to local SQLite first
    docs = crawl_day(date, db_path)

    if not docs:
        logger.info("No documents crawled")
        return 0

    # Convert to dicts for Supabase
    crawled_at = datetime.now().isoformat()
    doc_dicts = [
        {
            "package_id": doc.package_id,
            "granule_id": doc.granule_id,
            "title": doc.title,
            "doc_class": doc.doc_class,
            "publish_date": doc.publish_date,
            "metadata": doc.metadata,
            "pdf_url": doc.pdf_url,
            "html_url": doc.html_url,
            "details_url": doc.details_url,
            "summary": doc.summary,
            "crawled_at": crawled_at,
        }
        for doc in docs
    ]

    return sync_to_supabase(supabase, doc_dicts)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sync GovInfo documents to Supabase")
    parser.add_argument("--date", help="Specific date to crawl and sync (YYYY-MM-DD)")
    parser.add_argument(
        "--yesterday", action="store_true", help="Crawl and sync yesterday"
    )
    parser.add_argument(
        "--sync-only", action="store_true", help="Only sync existing SQLite data"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )

    args = parser.parse_args()

    supabase = get_supabase_client()

    if args.sync_only:
        count = sync_from_sqlite(supabase, args.db, args.date)
        logger.info(f"Synced {count} documents from SQLite to Supabase")
    elif args.yesterday:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        count = crawl_and_sync(supabase, yesterday, args.db)
        logger.info(f"Crawled and synced {count} documents for {yesterday}")
    elif args.date:
        count = crawl_and_sync(supabase, args.date, args.db)
        logger.info(f"Crawled and synced {count} documents for {args.date}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
