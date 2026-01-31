"""
Daily Firecrawl batch extraction job.

Fetches unprocessed documents from Supabase, runs firecrawl batch extraction,
and saves structured results back to Supabase.

Usage:
    uv run python scripts/extract.py
    uv run python scripts/extract.py --limit 100
    uv run python scripts/extract.py --date 2026-01-30
"""

import os
import logging
from datetime import datetime, timedelta
from enum import Enum

from dotenv import load_dotenv
from firecrawl import Firecrawl
from pydantic import BaseModel
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Firecrawl limits
BATCH_SIZE = 50  # firecrawl batch limit per request


class Sector(str, Enum):
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    TECH = "tech"
    ENERGY = "energy"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    OTHER = "other"


class Relevance(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StructuredOutput(BaseModel):
    title: str
    companies_mentioned: list[str]
    sector: list[Sector]
    relevance: list[Relevance]
    summary: str


EXTRACTION_PROMPT = """Analyze the provided document to extract high-value business insights, identifying all mentioned companies, stakeholders, and specific regulatory or market-driven deadlines. Provide a structured summary using bold bullet points that details main impacts on models, rephrase so that the summary is understandable by business audience."""


def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get(
        "SUPABASE_SERVICE_ROLE_API_KEY"
    )
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY required")
    return create_client(url, key)


def get_firecrawl_client() -> Firecrawl:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY is not set")
    return Firecrawl(api_key=api_key)


def fetch_unprocessed_documents(
    supabase: Client,
    limit: int | None = None,
    date: str | None = None,
) -> list[dict]:
    """Fetch documents that haven't been extracted yet."""
    # Left join to find documents without extractions
    query = (
        supabase.table("documents")
        .select("id, html_url, publish_date")
        .not_.is_("html_url", "null")
    )

    if date:
        query = query.eq("publish_date", date)

    # Only get docs without extractions - we'll filter in Python
    # since Supabase doesn't support NOT EXISTS easily
    if limit:
        query = query.limit(limit)

    result = query.execute()
    docs = result.data

    if not docs:
        return []

    # Get existing extraction document_ids
    doc_ids = [d["id"] for d in docs]
    existing = (
        supabase.table("extractions")
        .select("document_id")
        .in_("document_id", doc_ids)
        .execute()
    )
    existing_ids = {e["document_id"] for e in existing.data}

    # Filter out already processed
    unprocessed = [d for d in docs if d["id"] not in existing_ids]
    return unprocessed


def run_batch_extraction(
    firecrawl: Firecrawl,
    urls: list[str],
) -> dict:
    """Run firecrawl batch scrape with structured extraction."""
    logger.info(f"Starting batch extraction for {len(urls)} URLs...")

    result = firecrawl.batch_scrape(
        urls,
        formats=[
            {
                "type": "json",
                "schema": StructuredOutput.model_json_schema(),
                "prompt": EXTRACTION_PROMPT,
            }
        ],
        poll_interval=5,
    )

    return result


def save_extractions(
    supabase: Client,
    extractions: list[dict],
) -> int:
    """Save extraction results to Supabase."""
    if not extractions:
        return 0

    supabase.table("extractions").upsert(
        extractions,
        on_conflict="document_id",
    ).execute()

    return len(extractions)


def extract_documents(
    limit: int | None = None,
    date: str | None = None,
) -> int:
    """Main extraction pipeline."""
    supabase = get_supabase_client()
    firecrawl = get_firecrawl_client()

    # Fetch unprocessed docs
    docs = fetch_unprocessed_documents(supabase, limit=limit, date=date)
    if not docs:
        logger.info("No unprocessed documents found")
        return 0

    logger.info(f"Found {len(docs)} unprocessed documents")

    total_extracted = 0

    # Process in batches
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i : i + BATCH_SIZE]
        urls = [d["html_url"] for d in batch]
        url_to_doc = {d["html_url"]: d for d in batch}

        try:
            result = run_batch_extraction(firecrawl, urls)

            if result.status != "completed":
                logger.error(f"Batch failed with status: {result.status}")
                continue

            # Map results back to documents
            logger.debug(f"Result type: {type(result)}")
            logger.debug(f"Result attrs: {dir(result)}")
            logger.info(
                f"Batch status: {result.status}, total: {getattr(result, 'total', '?')}, completed: {getattr(result, 'completed', '?')}"
            )

            extractions = []
            for idx, item in enumerate(result.data):
                # Debug: log the item structure
                logger.debug(f"Item {idx} type: {type(item)}")
                logger.debug(f"Item {idx} attrs: {dir(item)}")
                if hasattr(item, "__dict__"):
                    logger.info(f"Item {idx} dict keys: {list(item.__dict__.keys())}")

                # firecrawl returns Document objects, not dicts
                metadata = getattr(item, "metadata", None)
                logger.debug(
                    f"Item {idx} metadata type: {type(metadata)}, value: {metadata}"
                )

                # Try different ways to get the URL
                url = None
                if isinstance(metadata, dict):
                    url = metadata.get("sourceURL")
                elif metadata is not None:
                    url = getattr(metadata, "sourceURL", None)
                    if url is None:
                        url = getattr(metadata, "source_url", None)
                    if url is None and hasattr(metadata, "__dict__"):
                        logger.info(f"Item {idx} metadata dict: {metadata.__dict__}")

                # Also check for url directly on item
                if url is None:
                    url = getattr(item, "url", None) or getattr(item, "sourceURL", None)

                logger.info(f"Item {idx} resolved URL: {url}")

                if not url or url not in url_to_doc:
                    logger.warning(f"Could not match result to document: {url}")
                    logger.warning(f"Expected URLs: {list(url_to_doc.keys())}")
                    continue

                doc = url_to_doc[url]
                json_data = getattr(item, "json", {}) or {}

                extractions.append(
                    {
                        "document_id": doc["id"],
                        "title": (
                            json_data.get("title")
                            if isinstance(json_data, dict)
                            else getattr(json_data, "title", None)
                        ),
                        "companies_mentioned": (
                            json_data.get("companies_mentioned", [])
                            if isinstance(json_data, dict)
                            else getattr(json_data, "companies_mentioned", [])
                        ),
                        "sectors": [
                            s.value if hasattr(s, "value") else s
                            for s in (
                                json_data.get("sector", [])
                                if isinstance(json_data, dict)
                                else getattr(json_data, "sector", [])
                            )
                        ],
                        "relevance": [
                            r.value if hasattr(r, "value") else r
                            for r in (
                                json_data.get("relevance", [])
                                if isinstance(json_data, dict)
                                else getattr(json_data, "relevance", [])
                            )
                        ],
                        "summary": (
                            json_data.get("summary")
                            if isinstance(json_data, dict)
                            else getattr(json_data, "summary", None)
                        ),
                        "raw_json": (
                            item.__dict__ if hasattr(item, "__dict__") else item
                        ),
                        "extracted_at": datetime.now().isoformat(),
                    }
                )

            saved = save_extractions(supabase, extractions)
            total_extracted += saved
            logger.info(f"Saved {saved} extractions (batch {i // BATCH_SIZE + 1})")

        except Exception as e:
            logger.error(f"Batch extraction failed: {e}")
            continue

    return total_extracted


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run Firecrawl batch extraction")
    parser.add_argument("--limit", type=int, help="Max documents to process")
    parser.add_argument(
        "--date", help="Only process documents from this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--yesterday", action="store_true", help="Process yesterday's documents"
    )

    args = parser.parse_args()

    date = args.date
    if args.yesterday:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    count = extract_documents(limit=args.limit, date=date)
    logger.info(f"Extraction complete. Processed {count} documents.")


if __name__ == "__main__":
    main()
