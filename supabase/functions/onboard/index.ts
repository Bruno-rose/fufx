/**
 * Onboard a new subscriber: semantic search → send welcome email with top 5 docs
 * Triggered by database webhook on subscriptions insert
 */ import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("NEW_SUPABASE_KEY");
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY");
const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
Deno.serve(async (req)=>{
  try {
    const payload = await req.json();
    const sub = payload.record;
    console.log(`Onboarding subscriber ${sub.id}: ${sub.email}`);
    // 1. Semantic search to find matching documents
    const query = buildSearchQuery(sub);
    console.log(`Search query: "${query}"`);
    const searchResults = await semanticSearch(query, 5, 0.01);
    if (!searchResults.length) {
      console.log("No matching documents found");
      return Response.json({
        ok: true,
        message: "No matches"
      });
    }
    console.log(`Found ${searchResults.length} matching documents`);
    // 2. Fetch full extraction data for matched documents
    const documentIds = searchResults.map((r)=>r.document_id);
    const { data: extractions } = await supabase.from("extractions").select("id, document_id, title, summary, sectors, relevance, companies_mentioned, documents!inner(html_url)").in("document_id", documentIds);
    if (!extractions?.length) {
      console.log("No extractions found for matched documents");
      return Response.json({
        ok: true,
        message: "No extractions"
      });
    }
    // 3. Filter by subscription criteria (sectors, relevance threshold)
    const filtered = filterExtractions(extractions, sub);
    if (!filtered.length) {
      console.log("No extractions match subscription criteria");
      return Response.json({
        ok: true,
        message: "No matching criteria"
      });
    }
    console.log(`${filtered.length} extractions match criteria`);
    // 4. Send welcome email
    const html = renderEmail(filtered, sub);
    await sendEmail(sub.email, `Welcome to Congress Signal: ${filtered.length} documents for you`, html);
    console.log(`Welcome email sent to ${sub.email}`);
    return Response.json({
      ok: true,
      documents: filtered.length
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
  if (sub.sectors?.length) parts.push(...sub.sectors);
  if (sub.keywords?.length) parts.push(...sub.keywords);
  return parts.length ? parts.join(" ") : "regulatory policy congressional";
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
const RELEVANCE_ORDER = {
  high: 3,
  medium: 2,
  low: 1
};
function filterExtractions(extractions, sub) {
  return extractions.filter((ext)=>{
    // Check sectors overlap (empty = match all)
    if (sub.sectors?.length) {
      const overlap = ext.sectors?.some((s)=>sub.sectors.includes(s));
      if (!overlap) return false;
    }
    // Check relevance threshold
    const threshold = sub.relevance_threshold || "medium";
    const thresholdVal = RELEVANCE_ORDER[threshold] || 2;
    const relevanceVal = RELEVANCE_ORDER[ext.relevance || ""] || 0;
    if (relevanceVal < thresholdVal) return false;
    return true;
  });
}
function mdToHtml(md) {
  if (!md) return "<p>No summary available.</p>";
  return md// Code blocks first (before other transforms)
  .replace(/```[\s\S]*?```/g, (m)=>`<pre style="background:#f4f4f4;padding:8px;border-radius:4px;overflow-x:auto;font-size:13px;">${m.slice(3, -3).trim()}</pre>`)// Inline code
  .replace(/`([^`]+)`/g, '<code style="background:#f4f4f4;padding:2px 6px;border-radius:3px;font-size:13px;">$1</code>')// Bold
  .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/__(.+?)__/g, '<strong>$1</strong>')// Italic
  .replace(/\*(.+?)\*/g, '<em>$1</em>').replace(/_(.+?)_/g, '<em>$1</em>')// Links
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color:#1a73e8;">$1</a>')// Unordered lists
  .replace(/^[\-\*] (.+)$/gm, '<li style="margin:4px 0;">$1</li>')// Ordered lists
  .replace(/^\d+\. (.+)$/gm, '<li style="margin:4px 0;">$1</li>')// Wrap consecutive <li> in <ul>
  .replace(/(<li[^>]*>.*<\/li>\n?)+/g, '<ul style="margin:8px 0;padding-left:20px;">$&</ul>')// Paragraphs (double newlines)
  .replace(/\n\n+/g, '</p><p style="margin:8px 0;">')// Single newlines to <br>
  .replace(/\n/g, '<br>')// Wrap in paragraph
  .replace(/^(.+)$/, '<p style="margin:8px 0;">$1</p>');
}
async function sendEmail(to, subject, html) {
  await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      from: "news-digest@congresssignal.com",
      to,
      subject,
      html
    })
  });
}
function renderEmail(items, sub) {
  const sectors = sub.sectors?.join(", ") || "all sectors";
  const keywords = sub.keywords?.join(", ") || "general updates";
  const itemsHtml = items.map((item)=>{
    const url = item.documents?.html_url || "#";
    const sectorList = item.sectors?.join(", ") || "N/A";
    const relevance = item.relevance || "N/A";
    const companies = item.companies_mentioned?.join(", ") || "None mentioned";
    return `
    <div style="margin-bottom: 24px; padding: 16px; border: 1px solid #e0e0e0; border-radius: 8px;">
      <h3 style="margin: 0 0 8px 0;">
        <a href="${url}" style="color: #1a73e8; text-decoration: none;">${item.title || "Untitled"}</a>
      </h3>
      <p style="margin: 0 0 8px 0; color: #666; font-size: 14px;">
        <strong>Sectors:</strong> ${sectorList} | <strong>Relevance:</strong> ${relevance}
      </p>
      <p style="margin: 0 0 12px 0; color: #666; font-size: 14px;">
        <strong>Companies:</strong> ${companies}
      </p>
      <div style="color: #333; font-size: 14px; line-height: 1.5;">${mdToHtml(item.summary)}</div>
    </div>
  `;
  }).join("");
  return `
  <!DOCTYPE html>
  <html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
  </head>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h1 style="color: #333; border-bottom: 2px solid #1a73e8; padding-bottom: 10px;">
      Welcome to Congress Signal
    </h1>
    <p style="color: #666; margin-bottom: 8px;">
      You're now subscribed to updates for <strong>${sectors}</strong>.
    </p>
    <p style="color: #666; margin-bottom: 24px;">
      Here are ${items.length} recent document${items.length === 1 ? "" : "s"} matching your interests: <strong>${keywords}</strong>
    </p>
    
    ${itemsHtml}
    
    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">
    <p style="color: #999; font-size: 12px;">
      You'll receive daily digests when new documents match your criteria.
      <a href="#unsubscribe" style="color: #999;">Unsubscribe</a>
    </p>
  </body>
  </html>`;
}
