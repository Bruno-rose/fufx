"""
Sync pro digests: find top-k documents for each pro subscription.

For verified, non-unsubscribed pro subscriptions, uses semantic search
based on company_type + keywords to find relevant documents and saves
references to extractions_pro.

Usage:
    uv run python scripts/sync_pro_digests.py
    uv run python scripts/sync_pro_digests.py --date 2026-01-31
    uv run python scripts/sync_pro_digests.py --top-k 5
    uv run python scripts/sync_pro_digests.py --dry-run
"""

import os
import logging
from datetime import datetime

import httpx
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

DEFAULT_TOP_K = 10
DEFAULT_MATCH_THRESHOLD = 0.5


def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_active_pro_subscriptions(supabase: Client) -> list[dict]:
    """Fetch verified, non-unsubscribed pro subscriptions."""
    result = (
        supabase.table("subscriptions_pro")
        .select("id, email, company_type, keywords")
        .eq("is_verified", True)
        .is_("unsubscribed_at", "null")
        .execute()
    )
    return result.data


def build_search_query(subscription: dict) -> str:
    """Build semantic search query from company_type and keywords."""
    parts = []

    if subscription.get("company_type"):
        parts.append(subscription["company_type"])

    keywords = subscription.get("keywords") or []
    if keywords:
        parts.extend(keywords)

    if not parts:
        # Fallback - shouldn't happen but just in case
        return "regulatory policy"

    return " ".join(parts)


def semantic_search(
    query: str, match_count: int = 10, match_threshold: float = 0.5
) -> list[dict]:
    """Call the semantic-search edge function."""
    url = f"{SUPABASE_URL}/functions/v1/semantic-search"
    headers = {
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "matchCount": match_count,
        "matchThreshold": match_threshold,
    }

    logger.debug(f"Semantic search payload: {payload}")

    response = httpx.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    logger.debug(f"Semantic search raw response: {data}")
    logger.debug(
        f"Response type: {type(data)}, length: {len(data) if isinstance(data, list) else 'N/A'}"
    )

    return data


def insert_extractions_pro(
    supabase: Client,
    subscription_id: int,
    document_ids: list[int],
    period_date: str,
    dry_run: bool = False,
) -> int:
    """Insert extraction references for a subscription. Returns count inserted."""
    if dry_run:
        logger.info(
            f"[DRY RUN] Would insert {len(document_ids)} docs for subscription {subscription_id}"
        )
        return len(document_ids)

    inserted = 0
    for doc_id in document_ids:
        try:
            supabase.table("extractions_pro").upsert(
                {
                    "subscription_pro_id": subscription_id,
                    "document_id": doc_id,
                    "period_date": period_date,
                },
                on_conflict="subscription_pro_id,document_id,period_date",
            ).execute()
            inserted += 1
        except Exception as e:
            logger.warning(
                f"Failed to insert doc {doc_id} for sub {subscription_id}: {e}"
            )

    return inserted


def sync_pro_digests(
    period_date: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    dry_run: bool = False,
) -> dict:
    """Main function to sync pro digests."""
    supabase = get_supabase_client()

    target_date = period_date or datetime.now().strftime("%Y-%m-%d")

    subscriptions = fetch_active_pro_subscriptions(supabase)
    if not subscriptions:
        logger.info("No active pro subscriptions found")
        return {"subscriptions": 0, "documents": 0}

    logger.info(f"Found {len(subscriptions)} active pro subscriptions")

    stats = {"subscriptions": 0, "documents": 0, "errors": 0}

    for sub in subscriptions:
        query = build_search_query(sub)
        logger.info(f"Subscription {sub['id']} ({sub['email']}): query='{query}'")

        try:
            results = semantic_search(
                query, match_count=top_k, match_threshold=match_threshold
            )
        except Exception as e:
            logger.error(f"Semantic search failed for subscription {sub['id']}: {e}")
            stats["errors"] += 1
            continue

        if not results:
            logger.info(f"No matches for subscription {sub['id']}")
            continue

        document_ids = [r["document_id"] for r in results]
        inserted = insert_extractions_pro(
            supabase, sub["id"], document_ids, target_date, dry_run=dry_run
        )

        stats["subscriptions"] += 1
        stats["documents"] += inserted
        logger.info(f"Inserted {inserted} documents for subscription {sub['id']}")

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sync pro subscription digests")
    parser.add_argument("--date", help="Period date (YYYY-MM-DD), defaults to today")
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of top documents to match (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_MATCH_THRESHOLD,
        help=f"Similarity threshold (default: {DEFAULT_MATCH_THRESHOLD})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually insert records"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    stats = sync_pro_digests(
        period_date=args.date,
        top_k=args.top_k,
        match_threshold=args.threshold,
        dry_run=args.dry_run,
    )
    logger.info(
        f"Done. Subscriptions processed: {stats['subscriptions']}, "
        f"Documents inserted: {stats['documents']}, Errors: {stats.get('errors', 0)}"
    )


if __name__ == "__main__":
    main()
