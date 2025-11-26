// Allow up to 60s for long-running backend analyses
export const maxDuration = 60;

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: Request) {
  const { id, messages, agents, mode, code, entry, chat_query } = await req.json();

  // Determine chat mode and derive chat_query when not provided
  const hasCode = typeof code === 'string' && code.trim().length > 0;
  // If there's no code provided, always use chat mode to avoid backend requiring code for analysis modes
  const forcedMode = !hasCode ? 'chat' : mode;
  const lastUser = Array.isArray(messages)
    ? [...messages].reverse().find((m: any) => (m?.role || '').toLowerCase() === 'user')
    : undefined;
  const derivedChatQuery = chat_query || (lastUser?.content ? String(lastUser.content) : undefined);

  // Proxy to Python backend, passing thread_id for stateful memory
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
    "x-thread-id": id ?? "",
  };
  if (derivedChatQuery) headers["x-chat-query"] = String(derivedChatQuery);

  const res = await fetch(`${BACKEND_URL}/explain`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      messages,
      thread_id: id,
      agents,
      mode: forcedMode,
      code,
      entry: entry || (forcedMode === 'chat' ? 'chat' : undefined),
      chat_query: derivedChatQuery,
    }),
  });

  if (!res.body) {
    return new Response("Backend did not return a stream", { status: 502 });
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  // Convert backend SSE (data: ...) into a plain text stream for AI SDK text transport
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
          for (const line of lines) {
            let s = line.trim();
            if (!s) continue;
            if (s.startsWith("data:")) s = s.slice(5).trim();
            if (s.startsWith(":::progress:")) continue; // drop progress in text stream
            if (!seen.has(s)) {
              seen.add(s);
              controller.enqueue(encoder.encode(s + "\n"));
            }
          }
        }
        if (buffer.trim().length > 0) {
          let s = buffer.trim();
          if (s.startsWith("data:")) s = s.slice(5).trim();
          if (!s.startsWith(":::progress:") && !seen.has(s)) {
            seen.add(s);
            controller.enqueue(encoder.encode(s + "\n"));
          }
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
