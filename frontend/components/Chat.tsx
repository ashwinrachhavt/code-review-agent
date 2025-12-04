"use client";

import { useState, useRef, useEffect } from "react";
import { streamFromRoute } from "../lib/streamingClient";
import ProgressBar from "../components/ProgressBar";
import CodeEditor from "../components/CodeEditor";
import { MemoryPanel } from "./MemoryPanel";
import {
    Conversation,
    ConversationContent,
    ConversationEmptyState,
    ConversationScrollButton,
} from "../components/ai-elements/conversation";
import { Message, MessageContent, MessageResponse, MessageToolbar, MessageActions, MessageAction } from "../components/ai-elements/message";
import { CopyIcon, RefreshCwIcon } from "lucide-react";

export type ChatMessage = {
    id?: string;
    role: "user" | "assistant";
    content: string;
};

// Helper to extract agent badge from message content
function extractAgentBadge(content: string): { badge: string | null; cleanContent: string } {
    const badgeMatch = content.match(/^\*\*([^*]+)\*\*\n\n/);
    if (badgeMatch) {
        return {
            badge: badgeMatch[1],
            cleanContent: content.slice(badgeMatch[0].length)
        };
    }
    return { badge: null, cleanContent: content };
}

export default function Chat() {
    const [code, setCode] = useState("");
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [progress, setProgress] = useState(0);
    const [running, setRunning] = useState(false);
    const [chatInput, setChatInput] = useState("");
    

    // Stable thread id for this Chat session to enable backend memory (client-only)
    const [threadId, setThreadId] = useState<string>("");
    // Backend-issued thread id (from x-thread-id). Use this to read persisted state.
    const [serverThreadId, setServerThreadId] = useState<string>("");
    const [mounted, setMounted] = useState(false);
    const abortRef = useRef<AbortController | null>(null);

    // Generate threadId on client to avoid SSR hydration mismatches
    useEffect(() => {
        setMounted(true);
        try {
            const key = "cra.threadId";
            let tid = typeof window !== 'undefined' ? window.sessionStorage.getItem(key) || "" : "";
            if (!tid) {
                if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
                    tid = crypto.randomUUID();
                } else {
                    tid = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
                }
                if (typeof window !== 'undefined') window.sessionStorage.setItem(key, tid);
            }
            setThreadId(tid);
        } catch {
            // Fallback if sessionStorage is unavailable
            const tid = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
            setThreadId(tid);
        }
    }, []);

    const handleRun = async (codeStr: string) => {
        // Cancel any existing stream
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        setCode(codeStr);
        setRunning(true);
        setProgress(5);

        // Fresh analysis
        setMessages([]);

        // Add user message with code
        const userMsg: ChatMessage = {
            id: Date.now().toString(),
            role: "user",
            content: codeStr,
        };
        setMessages([userMsg]);

        try {
            // Kick off review via /api/review to capture x-thread-id header
            const res = await fetch("/api/review", {
                method: "POST",
                headers: { "Accept": "text/event-stream", "Content-Type": "application/json" },
                body: JSON.stringify({ id: threadId, messages: [userMsg], code: codeStr }),
                signal: abortRef.current.signal,
            });

            const th = res.headers.get("x-thread-id");
            if (th) {
                if (th !== threadId) setThreadId(th);
                if (th !== serverThreadId) setServerThreadId(th);
            }

            if (!res.body) throw new Error("No response body for streaming");
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let eventLines: string[] = [];
            let assistantContent = "";
            setMessages((prev) => [...prev, { id: (Date.now() + 1).toString(), role: "assistant", content: "" }]);

            const emitPayload = (payload: string) => {
                if (!payload) return;
                if (payload.startsWith(':::progress:')) {
                    const m = payload.match(/:::progress:\s*(\d+)/);
                    if (m) setProgress(parseInt(m[1], 10));
                    return;
                }
                assistantContent += payload + "\n";
                setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === "assistant") {
                        return [...prev.slice(0, -1), { ...last, content: assistantContent }];
                    }
                    return [...prev, { id: (Date.now() + 2).toString(), role: "assistant", content: payload }];
                });
            };

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
                            emitPayload(eventLines.join('\n'));
                            eventLines = [];
                        }
                        continue;
                    }
                    if (line.startsWith('data:')) eventLines.push(line.slice(5).trimStart());
                    else emitPayload(line.trim());
                }
            }
            const tail = buffer.replace(/\r?\n$/, '');
            if (tail) {
                if (tail.startsWith('data:')) emitPayload(tail.slice(5).trimStart());
                else emitPayload(tail.trim());
            }
            setProgress(100);
        } catch (e) {
            console.error(e);
        } finally {
            setRunning(false);
        }
    };

    

    const handleChatSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const q = chatInput.trim();
        if (!q || running) return;

        // Cancel any existing stream
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        setRunning(true);
        setProgress(5);
        setChatInput("");

        // Add user message
        const userMsg: ChatMessage = {
            id: Date.now().toString(),
            role: "user",
            content: q
        };

        // Optimistically update UI
        setMessages((prev) => [...prev, userMsg]);

        try {
            let assistantContent = "";
            // Send full history + new message
            const history = [...messages, userMsg];

            await streamFromRoute(
                "/api/chat",
                { id: threadId, messages: history, chat_query: q },
                {
                    onChunk: (t) => {
                        assistantContent += t;
                        setMessages((prev) => {
                            const last = prev[prev.length - 1];
                            if (last && last.role === "assistant") {
                                return [
                                    ...prev.slice(0, -1),
                                    { ...last, content: assistantContent }
                                ];
                            }
                            return [
                                ...prev,
                                { id: (Date.now() + 1).toString(), role: "assistant", content: t }
                            ];
                        });
                    },
                    onProgress: (p) => setProgress(p),
                    onError: (e) => console.error(e),
                    onDone: () => setRunning(false),
                },
                { signal: abortRef.current.signal }
            );
        } catch (err) {
            console.error(err);
        } finally {
            setRunning(false);
        }
    };

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
    };

    return (
        <main style={{ maxWidth: 980, margin: "24px auto", padding: "0 16px" }}>
            <h1 style={{ fontSize: 22, marginBottom: 12 }}>Smart Multi‑Agent Chat</h1>
            <CodeEditor onRun={handleRun} disabled={running} />
            
            <ProgressBar value={progress} />
            {/* Lightweight memory panel for context visibility (client-only to prevent hydration mismatches) */}
            {mounted && serverThreadId && <MemoryPanel threadId={serverThreadId} />}
            <Conversation className="mt-4 max-h-[500px] overflow-y-auto" role="log">
                <ConversationContent>
                    {messages.length === 0 ? (
                        <ConversationEmptyState
                            title="No messages yet"
                            description="Run code analysis or ask a question to start the conversation."
                        />
                    ) : (
                        messages.map((msg, i) => {
                            const { badge, cleanContent } = msg.role === "assistant"
                                ? extractAgentBadge(msg.content)
                                : { badge: null, cleanContent: msg.content };

                            return (
                                <Message key={msg.id || i} from={msg.role}>
                                    <MessageContent>
                                        {msg.role === "assistant" ? (
                                            <>
                                                {badge && (
                                                    <div style={{
                                                        fontSize: '0.875rem',
                                                        fontWeight: 600,
                                                        marginBottom: '0.5rem',
                                                        color: '#6366f1'
                                                    }}>
                                                        {badge}
                                                    </div>
                                                )}
                                                <MessageResponse>{cleanContent}</MessageResponse>
                                            </>
                                        ) : (
                                            <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                                        )}
                                    </MessageContent>
                                    {msg.role === "assistant" && (
                                        <MessageActions>
                                            <MessageAction
                                                tooltip="Copy to clipboard"
                                                onClick={() => copyToClipboard(cleanContent)}
                                            >
                                                <CopyIcon />
                                            </MessageAction>
                                        </MessageActions>
                                    )}
                                </Message>
                            );
                        })
                    )}
                </ConversationContent>
                <ConversationScrollButton />
                <MessageToolbar>
                    {/* Simple input for follow‑up queries */}
                    <form onSubmit={handleChatSubmit} style={{ width: "100%" }}>
                        <input
                            type="text"
                            placeholder="Ask a follow‑up question..."
                            disabled={running}
                            value={chatInput}
                            onChange={(e) => setChatInput(e.currentTarget.value)}
                            style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid #ddd" }}
                        />
                    </form>
                </MessageToolbar>
            </Conversation>
        </main>
    );
}
