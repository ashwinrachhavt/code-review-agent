"use client";

import { useEffect, useState } from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { MessageSquare, Clock } from 'lucide-react';

interface Thread {
    thread_id: string;
    created_at: string;
    updated_at: string;
    summary?: string;
    file_count?: number;
}

interface ThreadSidebarProps {
    activeThreadId: string | null;
    onSelectThread: (threadId: string) => void;
    onNewThread: () => void;
}

export function ThreadSidebar({ activeThreadId, onSelectThread, onNewThread }: ThreadSidebarProps) {
    const [threads, setThreads] = useState<Thread[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadThreads();
        // Refresh list when active thread changes (new analysis persisted)
    }, [activeThreadId]);

    const loadThreads = async () => {
        try {
            const response = await fetch('http://localhost:8000/threads?limit=50');
            if (response.ok) {
                const data = await response.json();
                setThreads(data);
            }
        } catch (error) {
            console.error('Failed to load threads:', error);
        } finally {
            setLoading(false);
        }
    };

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString();
    };

    return (
        <div className="w-64 border-r bg-muted/10 flex flex-col h-full">
            <div className="p-4 border-b">
                <Button
                    onClick={onNewThread}
                    className="w-full"
                    variant="default"
                >
                    <MessageSquare className="w-4 h-4 mr-2" />
                    New Analysis
                </Button>
            </div>

            <ScrollArea className="flex-1">
                <div className="p-2 space-y-1">
                    {loading ? (
                        <div className="text-center text-sm text-muted-foreground py-8">
                            Loading threads...
                        </div>
                    ) : threads.length === 0 ? (
                        <div className="text-center text-sm text-muted-foreground py-8">
                            No threads yet
                        </div>
                    ) : (
                        threads.map((thread) => (
                            <button
                                key={thread.thread_id}
                                onClick={() => onSelectThread(thread.thread_id)}
                                className={`w-full text-left p-3 rounded-lg transition-colors ${activeThreadId === thread.thread_id
                                        ? 'bg-primary text-primary-foreground'
                                        : 'hover:bg-muted'
                                    }`}
                            >
                                <div className="flex items-start justify-between gap-2">
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium truncate">
                                            {thread.summary || 'Code Review'}
                                        </div>
                                        {thread.file_count && (
                                            <div className="text-xs opacity-70 mt-1">
                                                {thread.file_count} files
                                            </div>
                                        )}
                                    </div>
                                    <Clock className="w-3 h-3 opacity-50 flex-shrink-0 mt-0.5" />
                                </div>
                                <div className="text-xs opacity-60 mt-1">
                                    {formatDate(thread.updated_at || thread.created_at)}
                                </div>
                            </button>
                        ))
                    )}
                </div>
            </ScrollArea>
        </div>
    );
}
