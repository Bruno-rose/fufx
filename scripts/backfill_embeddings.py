"""Backfill embeddings by triggering updates on extractions without them.

Since gte-small runs in the edge function, we just need to trigger an update
on each row to invoke the webhook.
"""

import os
import logging
import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BATCH_SIZE = 50


def call_edge_function(extraction_id: int, summary: str) -> bool:
    """Call the generate-embedding edge function directly."""
    url = f"{SUPABASE_URL}/functions/v1/generate-embedding"
    headers = {
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "UPDATE",
        "table": "extractions",
        "record": {
            "id": extraction_id,
            "summary": summary,
            "summary_embedding": None,
        },
        "old_record": None,
    }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to call edge function for {extraction_id}: {e}")
        return False


def backfill():
    """Backfill embeddings for extractions without them."""
    # Get extractions without embeddings
    result = (
        supabase.table("extractions")
        .select("id, summary")
        .is_("summary_embedding", "null")
        .not_.is_("summary", "null")
        .limit(BATCH_SIZE)
        .execute()
    )

    if not result.data:
        logger.info("No extractions to backfill")
        return 0

    count = 0
    for row in result.data:
        if call_edge_function(row["id"], row["summary"]):
            count += 1
            logger.info(f"Generated embedding for extraction {row['id']}")

    return count


if __name__ == "__main__":
    total = 0
    while True:
        processed = backfill()
        total += processed
        if processed < BATCH_SIZE:
            break
    logger.info(f"Done. Total processed: {total}")
