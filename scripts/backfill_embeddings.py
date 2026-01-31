"""Backfill embeddings for existing extractions that don't have them."""
import os
import logging
from supabase import create_client
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai = OpenAI(api_key=OPENAI_API_KEY)

BATCH_SIZE = 100


def get_embedding(text: str) -> list[float]:
    """Generate embedding using OpenAI."""
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


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
        try:
            embedding = get_embedding(row["summary"])
            supabase.table("extractions").update(
                {"summary_embedding": embedding}
            ).eq("id", row["id"]).execute()
            count += 1
            logger.info(f"Generated embedding for extraction {row['id']}")
        except Exception as e:
            logger.error(f"Failed to generate embedding for {row['id']}: {e}")

    return count


if __name__ == "__main__":
    total = 0
    while True:
        processed = backfill()
        total += processed
        if processed < BATCH_SIZE:
            break
    logger.info(f"Done. Total processed: {total}")

