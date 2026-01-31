# pip install firecrawl-py

from enum import Enum
import os
import time

from firecrawl import Firecrawl
from pydantic import BaseModel

def get_firecrawl_client() -> Firecrawl:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY is not set")
    return Firecrawl(api_key=api_key)

class Sector(Enum):
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    TECH = "tech"
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
    relevance: list[Relevance]
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
                "prompt": """Analyze the provided document to extract high-value business insights, identifying all mentioned companies, stakeholders, and specific regulatory or market-driven deadlines. Provide a structured summary using bold bullet points that details main impacts on models, rephrase so that the summary is understandable by business audience.
      """,
            }
        ],
    )
    elapsed = time.perf_counter() - start_time
    print(doc)
    print(f"Request took {elapsed:.2f}s")


if __name__ == "__main__":
    scrape_govinfo_example()



# TODO: see batch scraping