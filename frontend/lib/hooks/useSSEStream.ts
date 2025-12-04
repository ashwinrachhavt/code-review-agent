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
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const chunk = decoder.decode(value, { stream: true });
              const lines = chunk.split('\n');

              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  const content = line.slice(6);

                  // Handle progress updates
                  if (content.startsWith(':::progress:')) {
                    const prog = parseInt(content.split(':')[2].trim(), 10);
                    setProgress(prog);
                    options.onProgress?.(prog);
                  } else if (content.trim()) {
                    // Regular content
                    setData((prev) => prev + content + '\n\n');
                    options.onChunk?.(content);
                  }
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
