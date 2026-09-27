import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const responseHeaders = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer" };
const error = (detail: string, status: number) => Response.json({ detail }, { status, headers: responseHeaders });

function localRequestOrigin(request: NextRequest): string | null {
  // Next's URL can contain the container address. The browser's Host retains
  // its actual destination; accept only loopback hosts, never forwarded hosts.
  const host = request.headers.get("host") ?? request.nextUrl.host;
  if (!/^(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?$/i.test(host) || !["http:", "https:"].includes(request.nextUrl.protocol)) return null;
  try { return new URL(`${request.nextUrl.protocol}//${host}`).origin; }
  catch { return null; }
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (process.env.NEURASIGN_ENV === "production" || process.env.K_SERVICE) return error("Not found.", 404);
  const { path } = await context.params;
  const endpoint = path.join("/");
  const readable = endpoint === "catalog" || /^models\/[a-z0-9_-]+\/records$/.test(endpoint);
  const writable = /^models\/[a-z0-9_-]+\/predict$/.test(endpoint);
  if (request.nextUrl.search || !(request.method === "GET" ? readable : request.method === "POST" && writable)) return error("Not found.", 404);
  const origin = request.headers.get("origin");
  if ((origin && origin !== localRequestOrigin(request)) || request.headers.get("sec-fetch-site") === "cross-site") return error("Same-origin requests are required.", 403);

  let body: string | undefined;
  if (request.method === "POST") {
    const length = request.headers.get("content-length");
    if (length && (!/^\d+$/.test(length) || Number(length) > 2048)) return error("Request body is too large.", 413);
    const reader = request.body?.getReader();
    if (!reader) return error("Choose a recorded example.", 422);
    const chunks: Uint8Array[] = [];
    let total = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > 2048) {
          void reader.cancel().catch(() => {});
          return error("Request body is too large.", 413);
        }
        chunks.push(value);
      }
      const input: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (!input || typeof input !== "object" || Array.isArray(input) || Object.keys(input).length !== 1 || !("record_id" in input) || typeof input.record_id !== "string" || !/^[A-Za-z0-9_.:-]{1,200}$/.test(input.record_id)) return error("Choose a valid recorded example.", 422);
      body = JSON.stringify({ record_id: input.record_id });
    } catch {
      return error("Invalid request body.", 400);
    }
  }

  try {
    const token = process.env.MODEL_ENGINE_TOKEN;
    const upstream = await fetch(`${(process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "")}/api/model-engine/${endpoint}`, {
      method: request.method,
      headers: { "Content-Type": "application/json", ...(token ? { "X-Model-Engine-Token": token } : {}) },
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(55000),
    });
    if (!upstream.headers.get("content-type")?.includes("application/json")) return error("The model service returned an invalid response.", 502);
    return new Response(upstream.body, { status: upstream.status, headers: { ...responseHeaders, "Content-Type": "application/json" } });
  } catch {
    return error("The model engine is unavailable. Check the local service and try again.", 503);
  }
}

export { proxy as GET, proxy as POST };
