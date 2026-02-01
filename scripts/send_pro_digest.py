"""
Pro digest email sender.

Fetches pro subscriptions and sends personalized emails with their
custom Firecrawl-generated summaries.

Usage:
    uv run python scripts/send_pro_digest.py
    uv run python scripts/send_pro_digest.py --dry-run
    uv run python scripts/send_pro_digest.py --date 2026-01-31
"""

import os
import logging
from datetime import datetime

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

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

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

    html = mistune.html(text)
    wrapped = f'{MARKDOWN_STYLES}<div class="summary">{html}</div>'

    try:
        return inline_styles(wrapped, strip_important=False)
    except Exception:
        return f"<div>{html}</div>"


def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_active_pro_subscriptions(supabase: Client) -> list[dict]:
    """Fetch verified, non-unsubscribed pro subscriptions."""
    result = (
        supabase.table("subscriptions_pro")
        .select("id, email, company_type, keywords, frequency")
        .eq("is_verified", True)
        .is_("unsubscribed_at", "null")
        .execute()
    )
    return result.data


def fetch_unsent_extractions_for_subscription(
    supabase: Client,
    subscription_id: int,
    period_date: str | None = None,
) -> list[dict]:
    """
    Fetch extractions_pro that have summaries but haven't been sent.
    Joins with documents for html_url and title.
    """
    query = (
        supabase.table("extractions_pro")
        .select(
            "id, summary, period_date, "
            "documents!inner(id, html_url, title, publish_date)"
        )
        .eq("subscription_pro_id", subscription_id)
        .not_.is_("summary", "null")
        .is_("sent_at", "null")
    )

    if period_date:
        query = query.eq("period_date", period_date)

    result = query.execute()
    return result.data


def mark_extractions_sent(
    supabase: Client,
    extraction_ids: list[int],
) -> bool:
    """Mark extractions as sent by setting sent_at timestamp."""
    try:
        supabase.table("extractions_pro").update(
            {"sent_at": datetime.now().isoformat()}
        ).in_("id", extraction_ids).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to mark extractions as sent: {e}")
        return False


def render_pro_email_html(
    extractions: list[dict],
    subscription: dict,
    period_date: str,
) -> str:
    """Render personalized pro email HTML from extractions."""
    company_type = subscription.get("company_type") or "your industry"
    keywords = subscription.get("keywords") or []
    keywords_str = ", ".join(keywords) if keywords else "regulatory updates"

    items_html = ""
    for ext in extractions:
        doc = ext.get("documents", {})
        url = doc.get("html_url", "#") if isinstance(doc, dict) else "#"
        title = doc.get("title", "Untitled") if isinstance(doc, dict) else "Untitled"

        items_html += f"""
        <div style="margin-bottom: 28px; padding: 20px; background: #fafbfc; border-left: 4px solid #1a73e8; border-radius: 0 8px 8px 0;">
            <h3 style="margin: 0 0 12px 0; font-size: 18px; color: #1a1a1a;">{title}</h3>
            <div style="color: #333; font-size: 14px; line-height: 1.6;">{md_to_email_html(ext.get('summary', ''))}</div>
            <a href="{url}" style="display: inline-block; margin-top: 12px; padding: 8px 16px; background: #1a73e8; color: #fff; text-decoration: none; border-radius: 6px; font-size: 13px; font-weight: 500;">View Document →</a>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 650px; margin: 0 auto; padding: 24px; background: #f5f5f5;">
        <div style="background: #fff; padding: 32px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
            <h1 style="color: #1a1a1a; margin: 0 0 8px 0; font-size: 24px;">
                Congress Signal Pro
            </h1>
            <p style="color: #666; margin: 0 0 24px 0; font-size: 14px;">
                Personalized insights for <strong>{company_type}</strong> · {period_date}
            </p>
            
            <div style="margin-bottom: 24px; padding: 16px; background: #e8f4f8; border-radius: 8px;">
                <p style="margin: 0; color: #444; font-size: 13px;">
                    📊 <strong>{len(extractions)} document{'' if len(extractions) == 1 else 's'}</strong> matched your interests: {keywords_str}
                </p>
            </div>

            {items_html if items_html else '<p style="color: #666;">No matching documents for this period.</p>'}
        </div>
        
        <div style="text-align: center; margin-top: 24px;">
            <p style="color: #999; font-size: 12px;">
                You're receiving this as a Congress Signal Pro subscriber.
                <a href="#unsubscribe" style="color: #999;">Unsubscribe</a>
            </p>
        </div>
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
                "from": "pro@congresssignal.com",
                "to": to,
                "subject": subject,
                "html": html,
            }
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send to {to}: {e}")
        return False


def send_pro_digests(
    period_date: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Main function to send pro digest emails."""
    supabase = get_supabase_client()

    target_date = period_date or datetime.now().strftime("%Y-%m-%d")

    subscriptions = fetch_active_pro_subscriptions(supabase)
    if not subscriptions:
        logger.info("No active pro subscriptions found")
        return {"sent": 0, "failed": 0, "skipped": 0}

    logger.info(f"Found {len(subscriptions)} active pro subscriptions")

    stats = {"sent": 0, "failed": 0, "skipped": 0}

    for sub in subscriptions:
        extractions = fetch_unsent_extractions_for_subscription(
            supabase, sub["id"], target_date
        )

        if not extractions:
            logger.info(f"No unsent extractions for {sub['email']}, skipping")
            stats["skipped"] += 1
            continue

        html = render_pro_email_html(extractions, sub, target_date)
        subject = f"Congress Signal Pro: {len(extractions)} insights for {target_date}"

        if send_email(sub["email"], subject, html, dry_run=dry_run):
            stats["sent"] += 1
            logger.info(f"Sent pro digest to {sub['email']} ({len(extractions)} items)")

            # Mark as sent (unless dry run)
            if not dry_run:
                extraction_ids = [e["id"] for e in extractions]
                mark_extractions_sent(supabase, extraction_ids)
        else:
            stats["failed"] += 1

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send pro digest emails")
    parser.add_argument("--date", help="Period date (YYYY-MM-DD), defaults to today")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually send emails or mark as sent",
    )

    args = parser.parse_args()

    stats = send_pro_digests(period_date=args.date, dry_run=args.dry_run)
    logger.info(
        f"Done. Sent: {stats['sent']}, Failed: {stats['failed']}, Skipped: {stats['skipped']}"
    )


if __name__ == "__main__":
    main()
