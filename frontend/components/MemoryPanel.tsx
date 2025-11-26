"use client";

import { useEffect, useState } from "react";

type HistoryItem = { role: string; content: string };

export function MemoryPanel({ threadId, baseUrl }: { threadId: string; baseUrl?: string }) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [hasReport, setHasReport] = useState(false);

  async function fetchHistory() {
    if (!threadId) return;
    try {
      // Prefer frontend proxy to avoid cross-origin/env coupling
      const res = await fetch(`/api/history?thread_id=${encodeURIComponent(threadId)}`);
      if (!res.ok) return;
      const data = await res.json();
      setHistory(Array.isArray(data.history) ? data.history : []);
      setHasReport(Boolean(data.has_report));
    } catch {}
  }

  useEffect(() => {
    fetchHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: 12,
      marginTop: 12,
      background: "var(--background)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>Context & Memory</strong>
        <button
          type="button"
          onClick={fetchHistory}
          style={{ fontSize: 12, opacity: 0.8 }}
          aria-label="Refresh"
        >
          Refresh
        </button>
      </div>
      <div style={{ fontSize: 12, marginTop: 6, color: "var(--muted-foreground)" }}>
        Thread: <code>{threadId}</code> · Messages: {history.length} · Has report: {hasReport ? "yes" : "no"}
      </div>
      {history.length > 0 && (
        <div style={{ maxHeight: 120, overflowY: "auto", marginTop: 8 }}>
          {history.slice(-6).map((h, i) => (
            <div key={i} style={{ marginBottom: 6 }}>
              <span style={{ fontWeight: 600 }}>{h.role}:</span> {h.content}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
