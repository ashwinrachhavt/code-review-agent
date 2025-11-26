// Stream completions directly from OpenAI to avoid SDK version mismatches

export const maxDuration = 60;

export async function POST(req: Request) {
  const { prompt } = await req.json();
  if (!prompt || typeof prompt !== 'string') {
    return new Response('Missing prompt', { status: 400 });
  }

  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return new Response('OPENAI_API_KEY not set', { status: 500 });
  }

  const upstream = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      stream: true,
      messages: [
        { role: 'system', content: 'You are an expert writing assistant. Respond with clean Markdown only.' },
        { role: 'user', content: prompt },
      ],
    }),
  });

  if (!upstream.body) {
    return new Response('No upstream body', { status: 502 });
  }

  // Convert OpenAI SSE stream (data: {...}) to plain text stream of content deltas
  const encoder = new TextEncoder();
  const reader = upstream.body.getReader();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const decoder = new TextDecoder();
      let buffer = '';
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split(/\n/);
          buffer = lines.pop() ?? '';
          for (const line of lines) {
            const s = line.trim();
            if (!s || !s.startsWith('data:')) continue;
            const data = s.slice(5).trim();
            if (data === '[DONE]') continue;
            try {
              const json = JSON.parse(data);
              const delta = json.choices?.[0]?.delta?.content;
              if (typeof delta === 'string' && delta.length > 0) {
                controller.enqueue(encoder.encode(delta));
              }
            } catch {
              // ignore malformed chunk
            }
          }
        }
      } catch (err) {
        controller.error(err);
        return;
      } finally {
        controller.close();
      }
    }
  });
  return new Response(stream, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-cache',
    },
  });
}
