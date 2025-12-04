"use client";

import { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ThreadSidebar } from '@/components/ThreadSidebar';
import { AnalyzeForm } from '@/components/AnalyzeForm';
import { ChatInterface } from '@/components/ChatInterface';
import { Progress } from '@/components/ui/progress';
import { useSSEStream } from '@/lib/hooks/useSSEStream';
import ReactMarkdown from 'react-markdown';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import ThreadDetails from '@/components/ThreadDetails';

export default function Page() {
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [showAnalysis, setShowAnalysis] = useState(false);
  const [fetchOptions, setFetchOptions] = useState<RequestInit>({});
  const [chatMessages, setChatMessages] = useState<any[]>([]);

  const qc = useQueryClient();

  const { data, progress, isLoading, threadId } = useSSEStream(streamUrl, {
    ...fetchOptions,
    onComplete: () => {
      if (threadId) {
        setActiveThreadId(threadId);
        // Refresh thread list and the specific thread after the backend persists
        qc.invalidateQueries({ queryKey: ['threads', 50] }).catch(() => {});
        qc.invalidateQueries({ queryKey: ['thread', threadId] }).catch(() => {});
      }
    },
  });

  // Activate chat as soon as the backend issues x-thread-id header
  // (no need to wait for the stream to finish)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (threadId && activeThreadId !== threadId) setActiveThreadId(threadId);
  }, [threadId]);

  const handleAnalyze = async (formData: { code?: string; files?: File[]; entry?: string; mode: string }) => {
    setShowAnalysis(true);
    setStreamUrl(null);
    setChatMessages([]);

    const agents = ['quality', 'bug', 'security'];
    let body: any = { agents, mode: formData.mode };

    if (formData.files && formData.files.length > 0) {
      // Read files as text and send via JSON to Next proxy (/api/review)
      const fileInputs = await Promise.all(
        formData.files.map(async (f) => ({ path: f.name, content: await f.text() }))
      );
      body = { ...body, files: fileInputs, source: 'folder' };
    } else if (formData.entry) {
      body = { ...body, entry: formData.entry };
    } else if (formData.code) {
      body = { ...body, code: formData.code };
    }

    setFetchOptions({
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify(body),
    });
    setStreamUrl('/api/review');
  };

  const handleSelectThread = async (threadId: string) => {
    setActiveThreadId(threadId);
    setShowAnalysis(true);
    setStreamUrl(null);
    // Query invalidation ensures data arrives via useQuery below
    qc.invalidateQueries({ queryKey: ['thread', threadId] }).catch(() => {});
  };

  const { data: activeThread } = useQuery<any>({
    queryKey: ['thread', activeThreadId],
    enabled: !!activeThreadId,
    queryFn: async () => {
      const res = await fetch(`/api/threads/${activeThreadId}`);
      if (!res.ok) throw new Error('failed to fetch thread');
      return res.json();
    },
  });

  useEffect(() => {
    if (activeThread && Array.isArray(activeThread.messages)) {
      setChatMessages(activeThread.messages);
    }
  }, [activeThread]);

  const handleNewThread = () => {
    setActiveThreadId(null);
    setShowAnalysis(false);
    setStreamUrl(null);
    setChatMessages([]);
  };

  return (
    <div className="flex h-screen bg-background">
      <ThreadSidebar
        activeThreadId={activeThreadId}
        onSelectThread={handleSelectThread}
        onNewThread={handleNewThread}
      />

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="border-b p-4">
          <h1 className="text-2xl font-bold">Code Review Agent</h1>
          <p className="text-sm text-muted-foreground">
            AI-powered code analysis with expert insights
          </p>
        </div>

        <div className="flex-1 overflow-hidden flex">
          {/* Main Content Area */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {!showAnalysis ? (
              <Card className="p-6">
                <h2 className="text-lg font-semibold mb-4">Start New Analysis</h2>
                <AnalyzeForm onSubmit={handleAnalyze} isLoading={isLoading} />
              </Card>
            ) : null}

            {isLoading && (
              <Card className="p-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Analyzing code...</span>
                    <span className="text-sm text-muted-foreground">{progress}%</span>
                  </div>
                  <Progress value={progress} className="w-full" />
                </div>
              </Card>
            )}

            {showAnalysis && (data || activeThread?.report_text) && (
              <Card className="p-6">
                <h2 className="text-lg font-semibold mb-4">Analysis Report</h2>
                <Separator className="mb-4" />
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown>{data || activeThread?.report_text || ''}</ReactMarkdown>
                </div>
              </Card>
            )}

            {showAnalysis && activeThread?.state && (
              <Card className="p-6">
                <h2 className="text-lg font-semibold mb-4">Analysis Insights</h2>
                <Separator className="mb-4" />
                <ThreadDetails thread={activeThread} />
              </Card>
            )}
          </div>

          {/* Chat Sidebar */}
          {showAnalysis && (
            <div className="w-96 border-l flex flex-col">
              <ChatInterface threadId={activeThreadId} initialMessages={chatMessages} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
