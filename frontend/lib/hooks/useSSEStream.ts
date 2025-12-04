import { useEffect, useState, useRef } from 'react';

interface SSEStreamOptions {
  onProgress?: (progress: number) => void;
  onChunk?: (chunk: string) => void;
  onComplete?: () => void;
  onError?: (error: Error) => void;
}

interface SSEStreamResult {
  data: string;
  progress: number;
  isLoading: boolean;
  error: Error | null;
  threadId: string | null;
}

export function useSSEStream(
  url: string | null,
  options: SSEStreamOptions & RequestInit = {}
): SSEStreamResult {
  const [data, setData] = useState<string>('');
  const [progress, setProgress] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!url) return;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setIsLoading(true);
    setError(null);
    setData('');
    setProgress(0);

    const { onProgress, onChunk, onComplete, onError, ...fetchOptions } = options;

    fetch(url, {
      ...fetchOptions,
      signal: abortController.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Extract thread ID from headers
        const tid = response.headers.get('x-thread-id');
        if (tid) setThreadId(tid);

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) {
          throw new Error('No response body');
        }

        const processStream = async () => {
          let buffer = '';
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              buffer += decoder.decode(value, { stream: true });
              // SSE events are delimited by a blank line
              const events = buffer.split('\n\n');
              buffer = events.pop() || '';

              for (const evt of events) {
                // Collect data lines within the event
                const dataLines = evt
                  .split('\n')
                  .filter((l) => l.startsWith('data: '))
                  .map((l) => l.slice(6));

                if (dataLines.length === 0) continue;
                const payload = dataLines.join('\n');

                // Progress indicator
                const pm = payload.match(/^:::progress:\s*(\d+)/);
                if (pm) {
                  const prog = parseInt(pm[1], 10);
                  if (!Number.isNaN(prog)) {
                    setProgress(prog);
                    options.onProgress?.(prog);
                  }
                  continue;
                }

                // Done marker — do not render, just complete
                if (payload.trim() === ':::done') {
                  setIsLoading(false);
                  options.onComplete?.();
                  continue;
                }

                // Normal content
                if (payload.trim()) {
                  setData((prev) => prev + payload + '\n\n');
                  options.onChunk?.(payload);
                }
              }
            }

            setIsLoading(false);
            options.onComplete?.();
          } catch (err) {
            if (err instanceof Error && err.name !== 'AbortError') {
              setError(err);
              setIsLoading(false);
              options.onError?.(err);
            }
          }
        };

        processStream();
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setError(err);
          setIsLoading(false);
          options.onError?.(err);
        }
      });

    return () => {
      abortController.abort();
    };
  }, [url]);

  return { data, progress, isLoading, error, threadId };
}
