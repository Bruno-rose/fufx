import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

// Use Supabase's built-in gte-small model (384 dims)
const session = new Supabase.ai.Session("gte-small");

interface ExtractionPayload {
  type: "INSERT" | "UPDATE";
  table: string;
  record: {
    id: number;
    summary: string;
    summary_embedding: number[] | null;
  };
  old_record: {
    id: number;
    summary: string;
    summary_embedding: number[] | null;
  } | null;
}

Deno.serve(async (req) => {
  try {
    const payload: ExtractionPayload = await req.json();
    const { record, old_record } = payload;

    // Skip if no summary
    if (!record.summary) {
      return new Response(JSON.stringify({ message: "No summary to embed" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Skip if summary hasn't changed and embedding exists
    if (
      old_record &&
      record.summary === old_record.summary &&
      record.summary_embedding
    ) {
      return new Response(
        JSON.stringify({ message: "Summary unchanged, skipping" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Generate embedding using built-in gte-small
    const embedding = await session.run(record.summary, {
      mean_pool: true,
      normalize: true,
    });

    // Update the record with the embedding
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    const { error } = await supabase
      .from("extractions")
      .update({ summary_embedding: JSON.stringify(embedding) })
      .eq("id", record.id);

    if (error) {
      throw new Error(`Supabase update error: ${error.message}`);
    }

    return new Response(
      JSON.stringify({
        message: "Embedding generated successfully",
        id: record.id,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }
    );
  } catch (error) {
    console.error("Error:", error);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
});
