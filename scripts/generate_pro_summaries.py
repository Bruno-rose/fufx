"""
Generate personalized summaries for pro extractions using Firecrawl.

Fetches extractions_pro entries without summaries, uses Firecrawl with
custom prompts based on subscription's company_type + keywords.

Usage:
    uv run python scripts/generate_pro_summaries.py
    uv run python scripts/generate_pro_summaries.py --date 2026-01-31
    uv run python scripts/generate_pro_summaries.py --limit 10
    uv run python scripts/generate_pro_summaries.py --dry-run
"""

import os
import logging
import time
from datetime import datetime

from dotenv import load_dotenv
from firecrawl import Firecrawl
from pydantic import BaseModel
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]


class SummaryOutput(BaseModel):
    summary: str


def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_firecrawl_client() -> Firecrawl:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY is not set")
    return Firecrawl(api_key=api_key)


def build_custom_prompt(company_type: str | None, keywords: list[str] | None) -> str:
    """Build a personalized prompt from subscription info."""
    company_type = company_type or "general business"
    keywords_str = (
        ", ".join(keywords) if keywords else "regulatory updates, policy changes"
    )

    return f"""My company operates in the {company_type} sector and seeks key business insights. 
Summarize this document, highlighting the most relevant information and explaining its potential impact on my business. 
Focus on {keywords_str} and provide actionable takeaways for decision-making.
Be concise but comprehensive. If the document is not relevant to my sector, state that clearly."""


def fetch_pending_extractions(
    supabase: Client,
    period_date: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    Fetch extractions_pro entries that need summaries generated.
    Joins with subscriptions_pro and documents for the required info.
    """
    # Build query for extractions without summaries
    query = (
        supabase.table("extractions_pro")
        .select(
            "id, subscription_pro_id, document_id, period_date, "
            "subscriptions_pro!inner(id, company_type, keywords), "
            "documents!inner(id, html_url, title)"
        )
        .is_("summary", "null")
    )

    if period_date:
        query = query.eq("period_date", period_date)

    if limit:
        query = query.limit(limit)

    result = query.execute()
    return result.data


def generate_summary(
    firecrawl: Firecrawl,
    html_url: str,
    company_type: str | None,
    keywords: list[str] | None,
) -> str | None:
    """Call Firecrawl to generate a personalized summary."""
    prompt = build_custom_prompt(company_type, keywords)

    try:
        start_time = time.perf_counter()
        doc = firecrawl.scrape(
            html_url,
            formats=[
                {
                    "type": "json",
                    "schema": SummaryOutput.model_json_schema(),
                    "prompt": prompt,
                }
            ],
        )
        elapsed = time.perf_counter() - start_time
        logger.debug(f"Firecrawl request took {elapsed:.2f}s")

        # Extract summary from response - firecrawl returns Document objects, not dicts
        json_data = getattr(doc, "json", None)
        if json_data:
            summary = (
                json_data.get("summary")
                if isinstance(json_data, dict)
                else getattr(json_data, "summary", None)
            )
            if summary:
                return summary

        logger.warning(f"Unexpected response structure: {doc}")
        return None

    except Exception as e:
        logger.error(f"Firecrawl error for {html_url}: {e}")
        return None


def update_extraction_summary(
    supabase: Client, extraction_id: int, summary: str
) -> bool:
    """Update the summary field for an extraction."""
    try:
        supabase.table("extractions_pro").update({"summary": summary}).eq(
            "id", extraction_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to update extraction {extraction_id}: {e}")
        return False


def generate_pro_summaries(
    period_date: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Main function to generate pro summaries."""
    supabase = get_supabase_client()
    firecrawl = get_firecrawl_client()

    extractions = fetch_pending_extractions(supabase, period_date, limit)

    if not extractions:
        logger.info("No pending extractions found")
        return {"processed": 0, "success": 0, "errors": 0}

    logger.info(f"Found {len(extractions)} extractions to process")

    stats = {"processed": 0, "success": 0, "errors": 0}

    for ext in extractions:
        extraction_id = ext["id"]
        sub = ext["subscriptions_pro"]
        doc = ext["documents"]

        html_url = doc.get("html_url")
        if not html_url:
            logger.warning(
                f"Extraction {extraction_id}: document has no html_url, skipping"
            )
            stats["errors"] += 1
            continue

        company_type = sub.get("company_type")
        keywords = sub.get("keywords")

        logger.info(
            f"Processing extraction {extraction_id}: "
            f"doc={doc.get('title', doc['id'])[:50]}, "
            f"company_type={company_type}"
        )

        if dry_run:
            prompt = build_custom_prompt(company_type, keywords)
            logger.info(
                f"[DRY RUN] Would call Firecrawl with prompt: {prompt[:100]}..."
            )
            stats["processed"] += 1
            stats["success"] += 1
            continue

        summary = generate_summary(firecrawl, html_url, company_type, keywords)
        stats["processed"] += 1

        if not summary:
            stats["errors"] += 1
            continue

        if update_extraction_summary(supabase, extraction_id, summary):
            stats["success"] += 1
            logger.info(
                f"Extraction {extraction_id}: summary saved ({len(summary)} chars)"
            )
        else:
            stats["errors"] += 1

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate pro extraction summaries")
    parser.add_argument("--date", help="Period date (YYYY-MM-DD) to filter extractions")
    parser.add_argument(
        "--limit", type=int, help="Max number of extractions to process"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually call Firecrawl or update DB",
    )

    args = parser.parse_args()

    stats = generate_pro_summaries(
        period_date=args.date,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    logger.info(
        f"Done. Processed: {stats['processed']}, "
        f"Success: {stats['success']}, Errors: {stats['errors']}"
    )


if __name__ == "__main__":
    main()
