export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
};

export async function streamChat(
  apiUrl: string,
  id: string,
  messages: ChatMessage[],
  handlers: {
    onText?: (text: string) => void;
    onError?: (err: unknown) => void;
    onDone?: () => void;
  } = {},
  options: { agents?: string[]; mode?: string; code?: string; entry?: string; chatQuery?: string } = {}
) {
  const res = await fetch(apiUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id,
      messages,
      agents: options.agents,
      mode: options.mode,
      code: options.code,
      entry: options.entry,
      chat_query: options.chatQuery,
    }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Chat API error: ${res.status} ${t}`);
  }
  if (!res.body) throw new Error('No response body');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      if (chunk) handlers.onText?.(chunk);
    }
    handlers.onDone?.();
  } catch (err) {
    handlers.onError?.(err);
    throw err;
  } finally {
    reader.releaseLock();
  }
}
