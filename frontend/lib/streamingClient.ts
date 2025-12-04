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
      ...(payload.thread_id ? { 'x-thread-id': String(payload.thread_id) } : {}),
      ...(payload.chat_query ? { 'x-chat-query': String(payload.chat_query) } : {}),
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
  // Accumulate current SSE event data lines until blank line
  let eventLines: string[] = [];

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Process line-by-line to respect SSE framing (blank line ends an event)
      let idx: number;
      while ((idx = buffer.indexOf('\n')) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        const line = raw.replace(/\r?$/, '');

        if (line === '') {
          // End of one event -> emit combined data
          if (eventLines.length) {
            const payload = eventLines.join('\n');
            if (payload.startsWith(':::progress:')) {
              const m = payload.match(/:::progress:\s*(\d+)/);
              if (m && handlers.onProgress) handlers.onProgress(parseInt(m[1], 10));
            } else if (payload.trim() === ':::done') {
              handlers.onDone?.();
            } else if (payload) {
              handlers.onChunk?.(payload + '\n');
            }
            eventLines = [];
          }
          continue;
        }

        if (line.startsWith('data:')) {
          eventLines.push(line.slice(5).trimStart());
        } else {
          // Fallback for non-SSE plain text streaming
          const content = line.trimEnd();
          if (!content) continue;
          if (content.startsWith(':::progress:')) {
            const m = content.match(/:::progress:\s*(\d+)/);
            if (m && handlers.onProgress) handlers.onProgress(parseInt(m[1], 10));
          } else if (content.trim() === ':::done') {
            handlers.onDone?.();
          } else {
            handlers.onChunk?.(content + '\n');
          }
        }
      }
    }
    // Flush any remaining partial event content
    const tail = buffer.replace(/\r?\n$/, '');
    if (tail) {
      if (tail.startsWith('data:')) {
        eventLines.push(tail.slice(5).trimStart());
        const payload = eventLines.join('\n');
        if (payload.startsWith(':::progress:')) {
          const m = payload.match(/:::progress:\s*(\d+)/);
          if (m && handlers.onProgress) handlers.onProgress(parseInt(m[1], 10));
        } else if (payload.trim() === ':::done') {
          handlers.onDone?.();
        } else if (payload) {
          handlers.onChunk?.(payload + '\n');
        }
      } else {
        const content = tail.trim();
        if (content) {
          if (content.startsWith(':::progress:')) {
            const m = content.match(/:::progress:\s*(\d+)/);
            if (m && handlers.onProgress) handlers.onProgress(parseInt(m[1], 10));
          } else if (content.trim() === ':::done') {
            handlers.onDone?.();
          } else {
            handlers.onChunk?.(content + '\n');
          }
        }
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

// Generic helper to stream from a Next.js route path (e.g., '/api/analyze' or '/api/chat').
export async function streamFromRoute(
  routePath: string,
  body: any,
  handlers: StreamHandlers = {},
  opts: { signal?: AbortSignal } = {}
) {
  const res = await fetch(routePath, {
    method: 'POST',
    headers: {
      'Accept': 'text/plain, text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body ?? {}),
    signal: opts.signal,
  });
  if (!res.body) throw new Error('No response body for streaming');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventLines: string[] = [];
  const emitData = (payload: string) => {
    if (!payload) return;
    if (payload.startsWith(':::progress:')) {
      const m = payload.match(/:::progress:\s*(\d+)/);
      if (m && handlers.onProgress) handlers.onProgress(parseInt(m[1], 10));
    } else if (payload.trim() === ':::done') {
      handlers.onDone?.();
    } else {
      handlers.onChunk?.(payload + '\n');
    }
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf('\n')) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        const line = raw.replace(/\r?$/, '');
        if (line === '') {
          if (eventLines.length) {
            emitData(eventLines.join('\n'));
            eventLines = [];
          }
          continue;
        }
        if (line.startsWith('data:')) {
          eventLines.push(line.slice(5).trimStart());
        } else {
          emitData(line.trim());
        }
      }
    }
    const tail = buffer.replace(/\r?\n$/, '');
    if (tail) {
      if (tail.startsWith('data:')) emitData(tail.slice(5).trimStart());
      else emitData(tail.trim());
    }
    handlers.onDone?.();
  } catch (err) {
    handlers.onError?.(err);
    throw err;
  } finally {
    reader.releaseLock();
  }
}
