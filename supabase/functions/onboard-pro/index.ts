/**
 * Onboard a new pro subscriber: semantic search → Firecrawl summary → send email
 * Triggered by database webhook on subscriptions_pro insert
 */ import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("NEW_SUPABASE_KEY");
const FIRECRAWL_API_KEY = Deno.env.get("FIRECRAWL_API_KEY");
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY");
const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
Deno.serve(async (req)=>{
  try {
    const payload = await req.json();
    const sub = payload.record;
    console.log(`Onboarding pro subscriber ${sub.id}: ${sub.email}`);
    const periodDate = new Date().toISOString().split("T")[0];
    // 1. Semantic search to find matching documents
    const query = buildSearchQuery(sub);
    console.log(`Search query: "${query}"`);
    const searchResults = await semanticSearch(query, 1, 0.5);
    if (!searchResults.length) {
      console.log("No matching documents found");
      return Response.json({
        ok: true,
        message: "No matches"
      });
    }
    console.log(`Found ${searchResults.length} matching documents`);
    // 2. Insert extractions_pro entries
    const documentIds = searchResults.map((r)=>r.document_id);
    for (const docId of documentIds){
      await supabase.from("extractions_pro").upsert({
        subscription_pro_id: sub.id,
        document_id: docId,
        period_date: periodDate
      }, {
        onConflict: "subscription_pro_id,document_id,period_date"
      });
    }
    // 3. Generate summaries with Firecrawl
    const { data: extractions } = await supabase.from("extractions_pro").select("id, document_id, documents!inner(id, html_url, title)").eq("subscription_pro_id", sub.id).eq("period_date", periodDate).is("summary", null);
    const summaries = [];
    for (const ext of extractions || []){
      const doc = ext.documents;
      const summary = await generateSummary(doc.html_url, sub.company_type, sub.keywords);
      if (summary) {
        await supabase.from("extractions_pro").update({
          summary
        }).eq("id", ext.id);
        summaries.push({
          id: ext.id,
          title: doc.title,
          summary,
          url: doc.html_url
        });
      }
    }
    console.log(`Generated ${summaries.length} summaries`);
    // 4. Send email
    if (summaries.length > 0) {
      const html = renderEmail(summaries, sub, periodDate);
      await sendEmail(sub.email, `Congress Signal Pro: ${summaries.length} insights for you`, html);
      // Mark as sent
      const ids = summaries.map((s)=>s.id);
      await supabase.from("extractions_pro").update({
        sent_at: new Date().toISOString()
      }).in("id", ids);
      console.log(`Email sent to ${sub.email}`);
    }
    return Response.json({
      ok: true,
      summaries: summaries.length
    });
  } catch (err) {
    console.error("Onboarding error:", err);
    return Response.json({
      error: String(err)
    }, {
      status: 500
    });
  }
});
function buildSearchQuery(sub) {
  const parts = [];
  if (sub.company_type) parts.push(sub.company_type);
  if (sub.keywords?.length) parts.push(...sub.keywords);
  return parts.length ? parts.join(" ") : "regulatory policy";
}
async function semanticSearch(query, matchCount, matchThreshold) {
  const res = await fetch(`${SUPABASE_URL}/functions/v1/semantic-search`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      query,
      matchCount,
      matchThreshold
    })
  });
  return res.json();
}
async function generateSummary(url, companyType, keywords) {
  const prompt = buildPrompt(companyType, keywords);
  try {
    const res = await fetch("https://api.firecrawl.dev/v1/scrape", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${FIRECRAWL_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        url,
        formats: [
          {
            type: "json",
            schema: {
              type: "object",
              properties: {
                summary: {
                  type: "string"
                }
              },
              required: [
                "summary"
              ]
            },
            prompt
          }
        ]
      })
    });
    const data = await res.json();
    return data?.data?.json?.summary || null;
  } catch (e) {
    console.error(`Firecrawl error for ${url}:`, e);
    return null;
  }
}
function buildPrompt(companyType, keywords) {
  const type = companyType || "general business";
  const kw = keywords?.length ? keywords.join(", ") : "regulatory updates, policy changes";
  return `My company operates in the ${type} sector and seeks key business insights. 
Summarize this document, highlighting the most relevant information and explaining its potential impact on my business. 
Focus on ${kw} and provide actionable takeaways for decision-making.
Be concise but comprehensive.`;
}
async function sendEmail(to, subject, html) {
  await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      from: "pro@congresssignal.com",
      to,
      subject,
      html
    })
  });
}
function renderEmail(items, sub, date) {
  const companyType = sub.company_type || "your industry";
  const keywords = sub.keywords?.join(", ") || "regulatory updates";
  const itemsHtml = items.map((item)=>`
    <div style="margin-bottom: 28px; padding: 20px; background: #fafbfc; border-left: 4px solid #1a73e8; border-radius: 0 8px 8px 0;">
      <h3 style="margin: 0 0 12px 0; font-size: 18px; color: #1a1a1a;">${item.title}</h3>
      <div style="color: #333; font-size: 14px; line-height: 1.6;">${item.summary}</div>
      <a href="${item.url}" style="display: inline-block; margin-top: 12px; padding: 8px 16px; background: #1a73e8; color: #fff; text-decoration: none; border-radius: 6px; font-size: 13px;">View Document →</a>
    </div>
  `).join("");
  return `
  <!DOCTYPE html>
  <html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 650px; margin: 0 auto; padding: 24px; background: #f5f5f5;">
    <div style="background: #fff; padding: 32px; border-radius: 12px;">
      <h1 style="color: #1a1a1a; margin: 0 0 8px 0; font-size: 24px;">Congress Signal Pro</h1>
      <p style="color: #666; margin: 0 0 24px 0; font-size: 14px;">
        Personalized insights for <strong>${companyType}</strong> · ${date}
      </p>
      <div style="margin-bottom: 24px; padding: 16px; background: #e8f4f8; border-radius: 8px;">
        <p style="margin: 0; color: #444; font-size: 13px;">
          📊 <strong>${items.length} document${items.length === 1 ? "" : "s"}</strong> matched: ${keywords}
        </p>
      </div>
      ${itemsHtml}
    </div>
  </body>
  </html>`;
}
