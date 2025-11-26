// Proxy conversation memory to Python backend
export const maxDuration = 15;

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const threadId = searchParams.get("thread_id") || "";
  const headers: Record<string, string> = {};
  if (threadId) headers["x-thread-id"] = threadId;

  const res = await fetch(
    `${BACKEND_URL}/explain/history?thread_id=${encodeURIComponent(threadId)}`,
    { headers }
  );

  return new Response(await res.text(), {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}

