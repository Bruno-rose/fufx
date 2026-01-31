# pip install firecrawl-py

from enum import Enum

from firecrawl import Firecrawl
from pydantic import BaseModel

firecrawl = Firecrawl(api_key="fc-858c765c3de342e6980ead5549ae181d")

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

# Scrape a website:
doc = firecrawl.scrape("https://www.govinfo.gov/content/pkg/FR-2026-01-29/html/2026-01817.htm", 
formats=[{
      "type": "json",
      "schema": StructuredOutput.model_json_schema(),
      "prompt": """Provide a structured output. The goal is to gain insights for companies on impact for their businesses.
      """
    }],)
print(doc)



# TODO: see batch scraping