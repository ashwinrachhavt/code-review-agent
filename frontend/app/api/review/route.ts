// Allow up to 60s for long-running backend analyses
export const maxDuration = 60;

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: Request) {
  const { id, messages, agents, mode, code, entry, chat_query, files } = await req.json();

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

  const body: any = {
    messages,
    thread_id: id,
    agents,
    mode: forcedMode,
    code,
    entry: entry || (forcedMode === 'chat' ? 'chat' : undefined),
    chat_query: derivedChatQuery,
  };
  if (Array.isArray(files) && files.length) {
    body.files = files.map((f: any) => ({ path: f.path, content: f.content }));
    body.source = 'folder';
  }

  const res = await fetch(`${BACKEND_URL}/explain`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!res.body) {
    return new Response("Backend did not return a stream", { status: 502 });
  }

  // Forward x-thread-id header from backend so client can persist it
  const threadHeader = res.headers.get('x-thread-id');
  const responseHeaders: Record<string, string> = {
    'Content-Type': res.headers.get('Content-Type') || 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache',
  };
  if (threadHeader) responseHeaders['x-thread-id'] = threadHeader;

  // Pass through the upstream stream as-is (SSE or plain text)
  return new Response(res.body, { headers: responseHeaders, status: res.status });
}
