"""
Daily email digest sender.

Fetches subscriptions and sends personalized emails with matching extractions.

Usage:
    uv run python scripts/send_digest.py
    uv run python scripts/send_digest.py --dry-run
    uv run python scripts/send_digest.py --date 2026-01-30
"""

import os
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
import mistune
from premailer import transform as inline_styles
import resend
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Relevance ordering for threshold comparison
RELEVANCE_ORDER = {"high": 3, "medium": 2, "low": 1}

# Styles for markdown elements in email
MARKDOWN_STYLES = """
<style>
    .summary ul, .summary ol { margin: 8px 0; padding-left: 20px; }
    .summary li { margin: 4px 0; color: #333; }
    .summary p { margin: 8px 0; }
    .summary strong, .summary b { font-weight: 600; }
    .summary code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 13px; font-family: monospace; }
    .summary a { color: #1a73e8; }
</style>
"""


def md_to_email_html(text: str) -> str:
    """Convert markdown to email-safe HTML with inline styles."""
    if not text:
        return "<p>No summary available.</p>"

    # Convert markdown to HTML
    html = mistune.html(text)

    # Wrap with class for styling, then inline the styles
    wrapped = f'{MARKDOWN_STYLES}<div class="summary">{html}</div>'

    try:
        return inline_styles(wrapped, strip_important=False)
    except Exception:
        # Fallback if premailer fails
        return f"<div>{html}</div>"


def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get(
        "SUPABASE_SERVICE_ROLE_API_KEY"
    )
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY required")
    return create_client(url, key)


def fetch_active_subscriptions(supabase: Client) -> list[dict]:
    """Fetch verified, non-unsubscribed subscriptions."""
    result = (
        supabase.table("subscriptions")
        .select("id, email, sectors, relevance_threshold, keywords")
        .eq("is_verified", True)
        .is_("unsubscribed_at", "null")
        .execute()
    )
    return result.data


def fetch_extractions_for_date(supabase: Client, date: str) -> list[dict]:
    """Fetch all extractions for documents published on a given date."""
    # Join extractions with documents to filter by publish_date
    result = (
        supabase.table("extractions")
        .select(
            "id, document_id, title, companies_mentioned, sectors, relevance, summary, documents(html_url, publish_date)"
        )
        .eq("documents.publish_date", date)
        .execute()
    )
    # Filter out nulls from the join (documents that don't match the date)
    return [e for e in result.data if e.get("documents")]


def matches_threshold(extraction_relevance: list[str], threshold: str) -> bool:
    """Check if any extraction relevance meets the threshold."""
    threshold_val = RELEVANCE_ORDER.get(threshold, 2)
    for rel in extraction_relevance:
        if RELEVANCE_ORDER.get(rel, 0) >= threshold_val:
            return True
    return False


def matches_sectors(extraction_sectors: list[str], sub_sectors: list[str]) -> bool:
    """Check if there's any sector overlap. Empty sub_sectors = match all."""
    if not sub_sectors:
        return True
    return bool(set(extraction_sectors) & set(sub_sectors))


def matches_keywords(extraction: dict, keywords: list[str]) -> bool:
    """Check if any keyword appears in title, summary, or companies. Empty = match all."""
    if not keywords:
        return True

    text = " ".join(
        [
            extraction.get("title") or "",
            extraction.get("summary") or "",
            " ".join(extraction.get("companies_mentioned") or []),
        ]
    ).lower()

    return any(kw.lower() in text for kw in keywords)


def filter_extractions_for_subscription(
    extractions: list[dict],
    subscription: dict,
) -> list[dict]:
    """Filter extractions that match a subscription's criteria."""
    matching = []
    for ext in extractions:
        if not matches_threshold(
            ext.get("relevance", []), subscription.get("relevance_threshold", "medium")
        ):
            continue
        if not matches_sectors(ext.get("sectors", []), subscription.get("sectors", [])):
            continue
        if not matches_keywords(ext, subscription.get("keywords", [])):
            continue
        matching.append(ext)
    return matching


def render_email_html(extractions: list[dict], date: str) -> str:
    """Render email HTML from extractions."""
    items_html = ""
    for ext in extractions:
        docs = ext.get("documents", {})
        url = docs.get("html_url", "#") if isinstance(docs, dict) else "#"

        sectors = ", ".join(ext.get("sectors", [])) or "N/A"
        relevance = ", ".join(ext.get("relevance", [])) or "N/A"
        companies = ", ".join(ext.get("companies_mentioned", [])) or "None mentioned"

        items_html += f"""
        <div style="margin-bottom: 24px; padding: 16px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h3 style="margin: 0 0 8px 0;">
                <a href="{url}" style="color: #1a73e8; text-decoration: none;">{ext.get('title', 'Untitled')}</a>
            </h3>
            <p style="margin: 0 0 8px 0; color: #666; font-size: 14px;">
                <strong>Sectors:</strong> {sectors} | <strong>Relevance:</strong> {relevance}
            </p>
            <p style="margin: 0 0 12px 0; color: #666; font-size: 14px;">
                <strong>Companies:</strong> {companies}
            </p>
            <div style="color: #333; font-size: 14px; line-height: 1.5;">{md_to_email_html(ext.get('summary', ''))}</div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #333; border-bottom: 2px solid #1a73e8; padding-bottom: 10px;">
            Congress Signal Daily Digest
        </h1>
        <p style="color: #666;">Documents for {date}</p>
        
        {items_html if items_html else '<p style="color: #666;">No matching documents for today.</p>'}
        
        <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">
        <p style="color: #999; font-size: 12px;">
            You're receiving this because you subscribed to Congress Signal alerts.
            <a href="#unsubscribe" style="color: #999;">Unsubscribe</a>
        </p>
    </body>
    </html>
    """


def send_email(to: str, subject: str, html: str, dry_run: bool = False) -> bool:
    """Send email via Resend."""
    if dry_run:
        logger.info(f"[DRY RUN] Would send to {to}: {subject}")
        return True

    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend.api_key:
        logger.error("RESEND_API_KEY not set")
        return False

    try:
        resend.Emails.send(
            {
                "from": "news-digest@congresssignal.com",
                "to": to,
                "subject": subject,
                "html": html,
            }
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send to {to}: {e}")
        return False


def send_digests(date: str | None = None, dry_run: bool = False) -> dict:
    """Main function to send digest emails to all subscribers."""
    supabase = get_supabase_client()

    target_date = date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Fetch all data
    subscriptions = fetch_active_subscriptions(supabase)
    if not subscriptions:
        logger.info("No active subscriptions found")
        return {"sent": 0, "failed": 0, "skipped": 0}

    logger.info(f"Found {len(subscriptions)} active subscriptions")

    extractions = fetch_extractions_for_date(supabase, target_date)
    logger.info(f"Found {len(extractions)} extractions for {target_date}")

    stats = {"sent": 0, "failed": 0, "skipped": 0}

    for sub in subscriptions:
        matching = filter_extractions_for_subscription(extractions, sub)

        if not matching:
            logger.info(f"No matching extractions for {sub['email']}, skipping")
            stats["skipped"] += 1
            continue

        html = render_email_html(matching, target_date)
        subject = f"Congress Signal: {len(matching)} updates for {target_date}"

        if send_email(sub["email"], subject, html, dry_run=dry_run):
            stats["sent"] += 1
            logger.info(f"Sent digest to {sub['email']} ({len(matching)} items)")
        else:
            stats["failed"] += 1

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send daily digest emails")
    parser.add_argument(
        "--date", help="Date to send digest for (YYYY-MM-DD), defaults to yesterday"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually send emails"
    )

    args = parser.parse_args()

    stats = send_digests(date=args.date, dry_run=args.dry_run)
    logger.info(
        f"Done. Sent: {stats['sent']}, Failed: {stats['failed']}, Skipped: {stats['skipped']}"
    )


if __name__ == "__main__":
    main()
