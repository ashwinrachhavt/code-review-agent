export type StreamHandlers = {
  onChunk?: (text: string) => void;
  onProgress?: (value: number) => void;
  onError?: (err: unknown) => void;
  onDone?: () => void;
};

export type ExplainPayload = {
  code: string;
  thread_id?: string;
  mode?: string;
  agents?: string[];
  chat_query?: string;
};

// Simple SSE parser for fetch streams (POST + text/event-stream)
export async function streamExplain(
  payload: ExplainPayload,
  handlers: StreamHandlers = {},
  opts: { baseUrl?: string; signal?: AbortSignal } = {}
) {
  const baseUrl = opts.baseUrl ?? '';
  const url = `${baseUrl}/explain`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      // Accept either SSE or plain text; backend may send text/plain
      'Accept': 'text/plain, text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    signal: opts.signal,
  });

  if (!res.body) {
    throw new Error('No response body for streaming');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Process line-by-line so we handle both SSE (`data: ...`) and plain text
      let idx: number;
      while ((idx = buffer.indexOf('\n')) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        const line = raw.trimEnd();
        if (!line) continue;

        // Normalize SSE data lines to plain
        const content = line.startsWith('data:') ? line.slice(5).trim() : line;

        if (content.startsWith(':::progress:')) {
          const m = content.match(/:::progress:\s*(\d+)/);
          if (m && handlers.onProgress) handlers.onProgress(parseInt(m[1], 10));
          continue;
        }
        handlers.onChunk?.(content + '\n');
      }
    }
    // Flush remaining buffer
    const tail = buffer.trim();
    if (tail) {
      const content = tail.startsWith('data:') ? tail.slice(5).trim() : tail;
      if (content.startsWith(':::progress:')) {
        const m = content.match(/:::progress:\s*(\d+)/);
        if (m && handlers.onProgress) handlers.onProgress(parseInt(m[1], 10));
      } else {
        handlers.onChunk?.(content + '\n');
      }
    }
    handlers.onDone?.();
  } catch (err) {
    handlers.onError?.(err);
    throw err;
  } finally {
    reader.releaseLock();
  }
}
