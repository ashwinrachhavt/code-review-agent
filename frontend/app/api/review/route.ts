// Allow up to 60s for long-running backend analyses
export const maxDuration = 60;

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export async function POST(req: Request) {
  const { id, messages, agents, mode, code, entry, chat_query, files } = await req.json();

  // Determine intent: analysis vs chat
  const hasCode = typeof code === 'string' && code.trim().length > 0;
  const hasFiles = Array.isArray(files) && files.length > 0;
  const hasEntry = typeof entry === 'string' && entry.trim().length > 0;
  const isChat = (!hasCode && !hasFiles && !hasEntry) || (String(mode).toLowerCase() === 'chat');

  const lastUser = Array.isArray(messages)
    ? [...messages].reverse().find((m: any) => (m?.role || '').toLowerCase() === 'user')
    : undefined;
  const derivedChatQuery = chat_query || (lastUser?.content ? String(lastUser.content) : undefined);

  // Proxy to Python backend, passing thread_id for stateful memory
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
    ...(id ? { 'x-thread-id': String(id) } : {}),
  };
  if (derivedChatQuery) headers["x-chat-query"] = String(derivedChatQuery);

  const body: any = {
    messages,
    thread_id: id,
    agents,
    mode: isChat ? 'chat' : (mode || 'orchestrator'),
    chat_query: derivedChatQuery,
  };
  if (hasCode) body.code = code;
  if (hasEntry) body.entry = entry;
  if (hasFiles) {
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
