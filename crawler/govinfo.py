"""
GovInfo Daily Crawler
Fetches document URLs and metadata from govinfo.gov
"""

import json
import sqlite3
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Iterator
import time
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# GovInfo search API
BASE_URL = "https://www.govinfo.gov"
SEARCH_URL = "https://www.govinfo.gov/wssearch/search"
PAGE_SIZE = 100

# Default database path
DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_DB_PATH = DATA_DIR / "govinfo.db"


@dataclass
class Document:
    package_id: str
    title: str
    doc_class: str
    publish_date: str
    metadata: str
    pdf_url: str | None
    html_url: str | None
    details_url: str
    granule_id: str | None = None
    summary: str | None = None


def build_search_query(start_date: str, end_date: str, offset: int = 0) -> dict:
    return {
        "query": f"publishdate:range({start_date},{end_date})",
        "offset": offset,
        "pageSize": PAGE_SIZE,
        "historical": False,
        "sortBy": "2",
    }


def fetch_search_results(
    client: httpx.Client, start_date: str, end_date: str, offset: int = 0
) -> dict:
    payload = build_search_query(start_date, end_date, offset)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "GovInfoCrawler/1.0",
    }
    resp = client.post(SEARCH_URL, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()


def parse_document(result: dict, query_date: str) -> Document:
    field_map = result.get("fieldMap", {})
    package_id = field_map.get("packageid", "")
    granule_id = field_map.get("granuleid")
    pdf_file = field_map.get("pdffile")
    html_file = field_map.get("htmlfile")

    pdf_url = f"{BASE_URL}/content/pkg/{package_id}/{pdf_file}" if pdf_file else None
    html_url = f"{BASE_URL}/content/pkg/{package_id}/{html_file}" if html_file else None
    details_url = f"{BASE_URL}/app/details/{package_id}"
    if granule_id:
        details_url = f"{BASE_URL}/app/details/{package_id}/{granule_id}"

    return Document(
        package_id=package_id,
        title=field_map.get("title", result.get("line1", "")),
        doc_class=field_map.get("collectionCode", ""),
        publish_date=query_date,
        metadata=result.get("line2", ""),
        pdf_url=pdf_url,
        html_url=html_url,
        details_url=details_url,
        granule_id=granule_id,
        summary=field_map.get("teaser", ""),
    )


def crawl_date_range(start_date: str, end_date: str) -> Iterator[Document]:
    """Crawl all documents published in the given date range."""
    offset = 0
    total_count = None
    query_date = start_date if start_date == end_date else start_date

    with httpx.Client(timeout=30.0) as client:
        while True:
            logger.info(f"Fetching offset={offset}...")
            try:
                data = fetch_search_results(client, start_date, end_date, offset)
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e}")
                break

            results = data.get("resultSet", [])
            if total_count is None:
                total_count = data.get("iTotalCount", 0)
                logger.info(f"Total documents: {total_count}")

            if not results:
                break

            for result in results:
                yield parse_document(result, query_date)

            offset += 1
            if offset * PAGE_SIZE >= total_count:
                break
            time.sleep(0.5)


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_id TEXT NOT NULL,
            granule_id TEXT,
            title TEXT,
            doc_class TEXT,
            publish_date TEXT NOT NULL,
            metadata TEXT,
            pdf_url TEXT,
            html_url TEXT,
            details_url TEXT,
            summary TEXT,
            crawled_at TEXT NOT NULL,
            UNIQUE(package_id, granule_id)
        )
    """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publish_date ON documents(publish_date)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_class ON documents(doc_class)")
    conn.commit()
    return conn


def save_documents(conn: sqlite3.Connection, docs: list[Document], crawled_at: str):
    for doc in docs:
        conn.execute(
            """INSERT OR REPLACE INTO documents 
               (package_id, granule_id, title, doc_class, publish_date, metadata, 
                pdf_url, html_url, details_url, summary, crawled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                doc.package_id,
                doc.granule_id,
                doc.title,
                doc.doc_class,
                doc.publish_date,
                doc.metadata,
                doc.pdf_url,
                doc.html_url,
                doc.details_url,
                doc.summary,
                crawled_at,
            ),
        )
    conn.commit()


def crawl_day(date: str, db_path: Path | None = None) -> list[Document]:
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    logger.info(f"Crawling documents for {date}...")
    conn = init_db(db_path)
    docs = list(crawl_date_range(date, date))
    logger.info(f"Found {len(docs)} documents")
    save_documents(conn, docs, datetime.now().isoformat())
    conn.close()
    logger.info(f"Saved to {db_path}")
    return docs


def crawl_range(
    start_date: str, end_date: str, db_path: Path | None = None
) -> list[Document]:
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    logger.info(f"Crawling {start_date} to {end_date}...")
    conn = init_db(db_path)
    docs = list(crawl_date_range(start_date, end_date))
    logger.info(f"Found {len(docs)} documents")
    save_documents(conn, docs, datetime.now().isoformat())
    conn.close()
    return docs


def export_to_json(db_path: Path, output_path: Path, date: str | None = None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if date:
        rows = conn.execute(
            "SELECT * FROM documents WHERE publish_date = ?", (date,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM documents").fetchall()
    with open(output_path, "w") as f:
        json.dump([dict(r) for r in rows], f, indent=2)
    conn.close()
    logger.info(f"Exported {len(rows)} documents")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GovInfo URL Crawler")
    parser.add_argument("--date", help="Date to crawl (YYYY-MM-DD)")
    parser.add_argument("--start-date", help="Start date")
    parser.add_argument("--end-date", help="End date")
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--yesterday", action="store_true")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--export", type=Path, help="Export to JSON")
    args = parser.parse_args()

    if args.export:
        export_to_json(args.db, args.export, args.date)
    elif args.today:
        crawl_day(datetime.now().strftime("%Y-%m-%d"), args.db)
    elif args.yesterday:
        crawl_day((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"), args.db)
    elif args.start_date and args.end_date:
        crawl_range(args.start_date, args.end_date, args.db)
    elif args.date:
        crawl_day(args.date, args.db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
