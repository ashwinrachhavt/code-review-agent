// Proxy chat requests to Python backend while preserving the SSE stream
export const maxDuration = 60;

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: Request) {
  const { id: bodyId, messages } = await req.json();
  const headerId = req.headers.get("x-thread-id") || undefined;
  const id = bodyId || headerId;

  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  };
  if (id) headers["x-thread-id"] = String(id);

  const res = await fetch(`${BACKEND_URL}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ thread_id: id, messages }),
  });

  if (!res.body) {
    return new Response("Backend did not return a stream", { status: 502 });
  }

  const responseHeaders: Record<string, string> = {
    "Content-Type": res.headers.get("Content-Type") || "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
  };
  const tid = res.headers.get("x-thread-id") || (id ? String(id) : null);
  if (tid) responseHeaders["x-thread-id"] = tid;

  return new Response(res.body, { status: res.status, headers: responseHeaders });
}
