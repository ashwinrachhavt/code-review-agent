// Proxy chat requests to Python backend and convert SSE to plain text stream
export const maxDuration = 60;

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: Request) {
  const { id, messages } = await req.json();

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

  // Convert backend SSE to plain text: join data: lines and strip progress
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let buffer = "";
      const seen = new Set<string>();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split(/\n/);
          buffer = lines.pop() ?? "";
          for (const raw of lines) {
            let s = raw.trim();
            if (!s) continue;
            if (s.startsWith("data:")) s = s.slice(5).trim();
            if (s.startsWith(":::progress:")) continue;
            if (!seen.has(s)) {
              seen.add(s);
              // Add a newline for plain text streaming compatibility
              controller.enqueue(encoder.encode(s + "\n"));
            }
          }
        }
        const tail = buffer.trim();
        if (tail && !tail.startsWith(":::progress:")) {
          const s = tail.startsWith("data:") ? tail.slice(5).trim() : tail;
          if (s && !seen.has(s)) controller.enqueue(encoder.encode(s + "\n"));
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
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  });
}

