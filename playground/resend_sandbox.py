


import os

from dotenv import load_dotenv
import resend
import firecrawl_prompt

load_dotenv()

StructuredOutput = firecrawl_prompt.StructuredOutput

resend.api_key = os.environ.get("RESEND_API_KEY", "")


r = resend.Emails.send({
  "from": "news-digest@congresssignal.com",
  "to": "ines.dormoy@gmail.com",
  "subject": "Hello World",
  "html": "<p>Congrats on sending your <strong>first email</strong>!</p>"
})
