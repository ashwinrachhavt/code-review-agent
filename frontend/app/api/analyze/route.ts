// Proxy analyze requests to Python backend and passthrough SSE/text stream
export const maxDuration = 120;

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: Request) {
  const { id, code, agents, mode } = await req.json();

  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  };
  if (id) headers["x-thread-id"] = String(id);

  const res = await fetch(`${BACKEND_URL}/analyze`, {
    method: "POST",
    headers,
    body: JSON.stringify({ thread_id: id, code, agents, mode: mode || "orchestrator" }),
  });

  if (!res.body) {
    return new Response("Backend did not return a stream", { status: 502 });
  }

  // Pass through stream as-is (SSE lines or plain text)
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      const encoder = new TextEncoder();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value) controller.enqueue(value);
        }
      } catch (err) {
        controller.error(err);
        return;
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  });
}

