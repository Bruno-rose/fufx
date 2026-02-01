"""
Webhook server for pro subscription onboarding.
Handles long-running tasks that timeout in Supabase Edge Functions.

Run with:
    uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
"""

import os
import logging
from datetime import datetime

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from firecrawl import Firecrawl
from pydantic import BaseModel
from supabase import create_client, Client
import resend
import mistune
from premailer import transform as inline_styles

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Congress Signal Pro Webhooks")

# Config
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # Optional auth


# Pydantic models
class SubscriptionRecord(BaseModel):
    id: int
    email: str
    company_type: str | None = None
    keywords: list[str] | None = None


class WebhookPayload(BaseModel):
    type: str  # INSERT, UPDATE, DELETE
    table: str
    record: dict
    old_record: dict | None = None
    schema_: str | None = None

    class Config:
        populate_by_name = True
        extra = "ignore"


class SummaryOutput(BaseModel):
    summary: str


# Clients
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_firecrawl() -> Firecrawl:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY not set")
    return Firecrawl(api_key=api_key)


# Email helpers
MARKDOWN_STYLES = """
<style>
    .summary ul, .summary ol { margin: 8px 0; padding-left: 20px; }
    .summary li { margin: 4px 0; color: #333; }
    .summary p { margin: 8px 0; }
    .summary strong, .summary b { font-weight: 600; }
    .summary code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
    .summary a { color: #1a73e8; }
</style>
"""


def md_to_email_html(text: str) -> str:
    if not text:
        return "<p>No summary available.</p>"
    html = mistune.html(text)
    wrapped = f'{MARKDOWN_STYLES}<div class="summary">{html}</div>'
    try:
        return inline_styles(wrapped, strip_important=False)
    except Exception:
        return f"<div>{html}</div>"


def render_email(
    items: list[dict],
    company_type: str | None,
    keywords: list[str] | None,
    date: str,
) -> str:
    company_type = company_type or "your industry"
    keywords_str = ", ".join(keywords) if keywords else "regulatory updates"

    items_html = "".join(
        f"""
        <div style="margin-bottom: 28px; padding: 20px; background: #fafbfc; border-left: 4px solid #1a73e8; border-radius: 0 8px 8px 0;">
            <h3 style="margin: 0 0 12px 0; font-size: 18px; color: #1a1a1a;">{item['title']}</h3>
            <div style="color: #333; font-size: 14px; line-height: 1.6;">{md_to_email_html(item['summary'])}</div>
            <a href="{item['url']}" style="display: inline-block; margin-top: 12px; padding: 8px 16px; background: #1a73e8; color: #fff; text-decoration: none; border-radius: 6px; font-size: 13px;">View Document →</a>
        </div>
        """
        for item in items
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 650px; margin: 0 auto; padding: 24px; background: #f5f5f5;">
        <div style="background: #fff; padding: 32px; border-radius: 12px;">
            <h1 style="color: #1a1a1a; margin: 0 0 8px 0; font-size: 24px;">Congress Signal Pro</h1>
            <p style="color: #666; margin: 0 0 24px 0; font-size: 14px;">
                Personalized insights for <strong>{company_type}</strong> · {date}
            </p>
            <div style="margin-bottom: 24px; padding: 16px; background: #e8f4f8; border-radius: 8px;">
                <p style="margin: 0; color: #444; font-size: 13px;">
                    📊 <strong>{len(items)} document{'s' if len(items) != 1 else ''}</strong> matched: {keywords_str}
                </p>
            </div>
            {items_html}
        </div>
    </body>
    </html>
    """


def send_email(to: str, subject: str, html: str) -> bool:
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
        logger.error(f"Failed to send email to {to}: {e}")
        return False


# Core pipeline functions
def build_search_query(company_type: str | None, keywords: list[str] | None) -> str:
    parts = []
    if company_type:
        parts.append(company_type)
    if keywords:
        parts.extend(keywords)
    return " ".join(parts) if parts else "regulatory policy"


def semantic_search(
    query: str, match_count: int = 5, match_threshold: float = 0.01
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
    response = httpx.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def build_firecrawl_prompt(company_type: str | None, keywords: list[str] | None) -> str:
    company_type = company_type or "general business"
    keywords_str = (
        ", ".join(keywords) if keywords else "regulatory updates, policy changes"
    )
    return f"""My company operates in the {company_type} sector and seeks key business insights. 
Summarize this document, highlighting the most relevant information and explaining its potential impact on my business. 
Focus on {keywords_str} and provide actionable takeaways for decision-making.
Be concise but comprehensive."""


def generate_summary(
    firecrawl: Firecrawl, url: str, company_type: str | None, keywords: list[str] | None
) -> str | None:
    """Generate summary using Firecrawl."""
    prompt = build_firecrawl_prompt(company_type, keywords)
    try:
        doc = firecrawl.scrape(
            url,
            formats=[
                {
                    "type": "json",
                    "schema": SummaryOutput.model_json_schema(),
                    "prompt": prompt,
                }
            ],
        )
        json_data = getattr(doc, "json", None)
        if json_data:
            summary = (
                json_data.get("summary")
                if isinstance(json_data, dict)
                else getattr(json_data, "summary", None)
            )
            if summary:
                return summary
        logger.warning(f"Unexpected Firecrawl response: {doc}")
        return None
    except Exception as e:
        logger.error(f"Firecrawl error for {url}: {e}")
        return None


def process_pro_onboarding(sub: SubscriptionRecord):
    """
    Full pro onboarding pipeline:
    1. Semantic search for matching documents
    2. Insert extractions_pro entries
    3. Generate Firecrawl summaries
    4. Send email
    """
    logger.info(f"Starting pro onboarding for {sub.email} (id={sub.id})")

    supabase = get_supabase()
    firecrawl = get_firecrawl()
    period_date = datetime.now().strftime("%Y-%m-%d")

    # 1. Semantic search
    query = build_search_query(sub.company_type, sub.keywords)
    logger.info(f"Search query: '{query}'")

    try:
        results = semantic_search(query, match_count=5, match_threshold=0.01)
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return

    if not results:
        logger.info(f"No matching documents for {sub.email}")
        return

    logger.info(f"Found {len(results)} matching documents")

    # 2. Insert extractions_pro
    document_ids = [r["document_id"] for r in results]
    for doc_id in document_ids:
        try:
            supabase.table("extractions_pro").upsert(
                {
                    "subscription_pro_id": sub.id,
                    "document_id": doc_id,
                    "period_date": period_date,
                },
                on_conflict="subscription_pro_id,document_id,period_date",
            ).execute()
        except Exception as e:
            logger.warning(f"Failed to upsert extraction for doc {doc_id}: {e}")

    # 3. Fetch extractions needing summaries and generate them
    result = (
        supabase.table("extractions_pro")
        .select("id, document_id, documents!inner(id, html_url, title)")
        .eq("subscription_pro_id", sub.id)
        .eq("period_date", period_date)
        .is_("summary", "null")
        .execute()
    )

    extractions = result.data or []
    summaries = []

    for ext in extractions:
        doc = ext.get("documents", {})
        html_url = doc.get("html_url")
        if not html_url:
            continue

        summary = generate_summary(firecrawl, html_url, sub.company_type, sub.keywords)
        if summary:
            try:
                supabase.table("extractions_pro").update({"summary": summary}).eq(
                    "id", ext["id"]
                ).execute()
                summaries.append(
                    {
                        "id": ext["id"],
                        "title": doc.get("title", "Untitled"),
                        "summary": summary,
                        "url": html_url,
                    }
                )
            except Exception as e:
                logger.error(
                    f"Failed to update summary for extraction {ext['id']}: {e}"
                )

    logger.info(f"Generated {len(summaries)} summaries for {sub.email}")

    # 4. Send email
    if summaries:
        html = render_email(summaries, sub.company_type, sub.keywords, period_date)
        subject = f"Congress Signal Pro: {len(summaries)} insights for you"

        if send_email(sub.email, subject, html):
            # Mark as sent
            ids = [s["id"] for s in summaries]
            try:
                supabase.table("extractions_pro").update(
                    {"sent_at": datetime.now().isoformat()}
                ).in_("id", ids).execute()
            except Exception as e:
                logger.error(f"Failed to mark extractions as sent: {e}")
            logger.info(f"Email sent to {sub.email}")
        else:
            logger.error(f"Failed to send email to {sub.email}")


# API endpoints
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhooks/pro-onboard")
async def webhook_pro_onboard(request: Request, background_tasks: BackgroundTasks):
    """
    Handle subscriptions_pro INSERT webhook from Supabase.
    Runs the full onboarding pipeline in the background.
    """
    # Optional: verify webhook secret
    if WEBHOOK_SECRET:
        auth_header = request.headers.get("x-webhook-secret", "")
        if auth_header != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        body = await request.json()
        payload = WebhookPayload(**body)
    except Exception as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    if payload.type != "INSERT" or payload.table != "subscriptions_pro":
        logger.warning(f"Ignoring webhook: type={payload.type}, table={payload.table}")
        return {"ok": True, "message": "Ignored"}

    try:
        sub = SubscriptionRecord(**payload.record)
    except Exception as e:
        logger.error(f"Invalid subscription record: {e}")
        raise HTTPException(status_code=400, detail="Invalid subscription record")

    # Run in background so webhook returns quickly
    background_tasks.add_task(process_pro_onboarding, sub)

    return {"ok": True, "message": f"Processing subscription {sub.id}"}


@app.post("/webhooks/pro-digest")
async def webhook_pro_digest(request: Request, background_tasks: BackgroundTasks):
    """
    Trigger daily pro digest processing.
    Can be called by a cron job or manual trigger.
    """
    if WEBHOOK_SECRET:
        auth_header = request.headers.get("x-webhook-secret", "")
        if auth_header != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Import and run the digest scripts
    from scripts.sync_pro_digests import sync_pro_digests
    from scripts.generate_pro_summaries import generate_pro_summaries
    from scripts.send_pro_digest import send_pro_digests

    async def run_digest_pipeline():
        try:
            logger.info("Starting pro digest pipeline")

            # Step 1: Sync digests
            sync_stats = sync_pro_digests()
            logger.info(f"Sync complete: {sync_stats}")

            # Step 2: Generate summaries
            summary_stats = generate_pro_summaries()
            logger.info(f"Summaries complete: {summary_stats}")

            # Step 3: Send emails
            send_stats = send_pro_digests()
            logger.info(f"Sending complete: {send_stats}")

        except Exception as e:
            logger.error(f"Digest pipeline error: {e}")

    background_tasks.add_task(run_digest_pipeline)
    return {"ok": True, "message": "Digest pipeline started"}
