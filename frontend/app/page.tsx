"use client";

import { useState, useEffect } from 'react';
import { ThreadSidebar } from '@/components/ThreadSidebar';
import { AnalyzeForm } from '@/components/AnalyzeForm';
import { ChatInterface } from '@/components/ChatInterface';
import { Progress } from '@/components/ui/progress';
import { useSSEStream } from '@/lib/hooks/useSSEStream';
import ReactMarkdown from 'react-markdown';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';

export default function Page() {
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [showAnalysis, setShowAnalysis] = useState(false);
  const [fetchOptions, setFetchOptions] = useState<RequestInit>({});
  const [chatMessages, setChatMessages] = useState<any[]>([]);

  const { data, progress, isLoading, threadId } = useSSEStream(streamUrl, {
    ...fetchOptions,
    onComplete: () => {
      if (threadId) setActiveThreadId(threadId);
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
    setChatMessages([]); // Reset chat for new analysis

    // Small timeout to reset stream if needed
    setTimeout(() => {
      if (formData.files) {
        // Upload mode
        const data = new FormData();
        formData.files.forEach((file) => data.append('files', file));
        data.append('mode', formData.mode);
        data.append('agents', 'quality,bug,security');

        setFetchOptions({
          method: 'POST',
          body: data,
        });
        setStreamUrl('http://localhost:8000/explain/upload');
      } else {
        // Paste or Folder mode
        const body: any = {
          mode: formData.mode,
          agents: ['quality', 'bug', 'security'],
        };

        if (formData.code) body.code = formData.code;
        if (formData.entry) body.entry = formData.entry;

        setFetchOptions({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        setStreamUrl('http://localhost:8000/explain');
      }
    }, 50);
  };

  const handleSelectThread = async (threadId: string) => {
    setActiveThreadId(threadId);
    setShowAnalysis(true);
    setStreamUrl(null); // Stop any current stream

    // Load thread data
    try {
      const response = await fetch(`http://localhost:8000/threads/${threadId}`);
      if (response.ok) {
        const threadData = await response.json();
        if (threadData.messages) {
          setChatMessages(threadData.messages);
        } else {
          setChatMessages([]);
        }
      }
    } catch (error) {
      console.error('Failed to load thread:', error);
      setChatMessages([]);
    }
  };

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

            {showAnalysis && data && (
              <Card className="p-6">
                <h2 className="text-lg font-semibold mb-4">Analysis Report</h2>
                <Separator className="mb-4" />
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown>{data}</ReactMarkdown>
                </div>
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
