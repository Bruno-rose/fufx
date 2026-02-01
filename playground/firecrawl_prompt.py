# pip install firecrawl-py
# uv run python playground/firecrawl_prompt.py
# uv run python playground/firecrawl_prompt.py --custom


from enum import Enum
import os
import time

from dotenv import load_dotenv

from firecrawl import Firecrawl
from pydantic import BaseModel

def get_firecrawl_client() -> Firecrawl:
    load_dotenv()
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY is not set")
    return Firecrawl(api_key=api_key)

class Sector(Enum):
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    TECH = "tech"
    AEROSPACE = "aerospace"
    AGRICULTURE = "agriculture"
    EDUCATION = "education"
    ENVIRONMENT = "environment"
    ENERGY = "energy"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    OTHER = "other"

class Relevance(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class StructuredOutput(BaseModel):
    title: str
    companies_mentioned: list[str]
    sector: list[Sector]
    relevance: Relevance
    summary: str


class SummaryOutput(BaseModel):
    summary: str

def scrape_govinfo_example():
    firecrawl = get_firecrawl_client()
    # Scrape a website:
    start_time = time.perf_counter()
    doc = firecrawl.scrape(
        "https://www.govinfo.gov/content/pkg/FR-2026-01-29/html/2026-01817.htm",
        formats=[
            {
                "type": "json",
                "schema": StructuredOutput.model_json_schema(),
                "prompt": """Analyze the provided document and produce a structured business summary with the following outputs:

1. **Title**
   - Rephrase the title to clearly describe the business nature of the document (e.g., regulation change, policy update, product launch, market rule change).

2. **Companies Mentioned**
   - List all explicitly named companies or organizations.

3. **Sector Classification**
   - Assign one or more sectors based on the PRIMARY business activities directly impacted by the document.

4. **Business Relevance**
   - Classify relevance based on **expected business impact**, not general interest:
     - HIGH: direct regulatory, financial, or operational impact; requires action or decision
     - MEDIUM: indirect impact, emerging trend, or strategic importance
     - LOW: informational or minimal business impact

5. **Summary**
   - Provide a concise, business-friendly summary using **bold bullet points**.
   - Group key policies or changes by sector.
   - Clearly state any regulatory or market-driven deadlines.
   - Focus on implications for businesses rather than legal or technical detail.

Be precise, conservative, and consistent when assigning sector and relevance.""",
            }
        ],
    )
    elapsed = time.perf_counter() - start_time
    print(doc)
    print(f"Request took {elapsed:.2f}s")


COMPANY_TYPE="pharmaceutical"
KEYWORDS="drugs, healthcare, pharmaceutical"
CUSTOM_PROMPT = f"""My company operates in the {COMPANY_TYPE} sector and seeks key business insights. Summarize this document, highlighting the most relevant information and explaining its potential impact on my business. Focus on {KEYWORDS} and provide actionable takeaways for decision-making."""

def scrape_custom_example():
    firecrawl = get_firecrawl_client()
    start_time = time.perf_counter()
    doc = firecrawl.scrape(
        "https://www.govinfo.gov/content/pkg/FR-2026-01-29/html/2026-01817.htm",
        formats=[
            {
                "type": "json",
                "schema": SummaryOutput.model_json_schema(),
                "prompt": CUSTOM_PROMPT,
            }
        ],
    )
    elapsed = time.perf_counter() - start_time
    print(doc)
    print(f"Request took {elapsed:.2f}s")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Firecrawl scrape example")
    parser.add_argument(
        "--custom",
        action="store_true",
        help="Use the custom prompt + summary-only schema",
    )
    args = parser.parse_args()

    if args.custom:
        scrape_custom_example()
    else:
        scrape_govinfo_example()
