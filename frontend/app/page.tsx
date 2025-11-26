"use client";

import { useRef, useState } from 'react';
import CodeEditor from '../components/CodeEditor';
import ReviewPanel from '../components/ReviewPanel';
import ProgressBar from '../components/ProgressBar';
import { streamExplain } from '../lib/streamingClient';

export default function Page() {
  const [progress, setProgress] = useState(0);
  const [content, setContent] = useState('');
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function run(code: string) {
    // Cancel any existing stream
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setContent('');
    setProgress(5);
    setRunning(true);
    // Keep single‑page flow; no separate chat panel
    try {
      await streamExplain(
        { code },
        {
          onChunk: (t) => setContent((c) => c + t),
          onProgress: (p) => setProgress(p),
          onError: (e) => setContent((c) => c + `\n\n[error] ${String(e)}`),
          onDone: () => setRunning(false),
        },
        { signal: abortRef.current.signal, baseUrl: process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000' }
      );
    } catch (e) {
      setRunning(false);
    }
  }

  return (
    <main style={{ maxWidth: 980, margin: '24px auto', padding: '0 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ fontSize: 22, marginBottom: 12 }}>Code Review (Streaming)</h1>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
        <CodeEditor onRun={run} disabled={running} />
        <ProgressBar value={progress} />
        <ReviewPanel content={content} />
        {/* Single-Page App: review only; chat UI removed */}
      </div>
    </main>
  );
}
