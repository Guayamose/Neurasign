import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (path.some(segment => !/^[A-Za-z0-9_-]+$/.test(segment))) {
    return Response.json({ detail: "Invalid endpoint." }, { status: 400 });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const length = request.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > 131072)) {
    return Response.json({ detail: "Request body is too large." }, { status: 413 });
  }
  let body: string | undefined;
  if (request.method !== "GET" && request.method !== "HEAD" && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > 131072) {
          void reader.cancel().catch(() => {});
          return Response.json({ detail: "Request body is too large." }, { status: 413 });
        }
        chunks.push(value);
      }
      body = Buffer.concat(chunks).toString("utf8");
    } catch {
      return Response.json({ detail: "Incomplete request body." }, { status: 400 });
    }
  }
  try {
    const upstream = await fetch(`${base}/api/v1/${path.join("/")}${request.nextUrl.search}`, {
      method: request.method,
      headers: { "Content-Type": "application/json", ...(request.headers.get("authorization") ? { Authorization: request.headers.get("authorization")! } : {}) },
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(path[0] === "gateway" && path[1] === "integrations" && path[3] === "sync" ? 55000 : 25000),
    });
    return new Response(upstream.body, { status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", ...(upstream.headers.get("content-security-policy") ? { "Content-Security-Policy": upstream.headers.get("content-security-policy")! } : {}) } });
  } catch {
    return Response.json({ detail: "The workspace service is temporarily unavailable. Please retry." }, { status: 503 });
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
