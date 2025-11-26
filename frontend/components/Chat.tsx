"use client";

import { useState, useRef } from "react";
import { streamExplain } from "../lib/streamingClient";
import ProgressBar from "../components/ProgressBar";
import CodeEditor from "../components/CodeEditor";
import {
    Conversation,
    ConversationContent,
    ConversationEmptyState,
    ConversationScrollButton,
} from "../components/ai-elements/conversation";
import { Message, MessageContent, MessageResponse, MessageToolbar } from "../components/ai-elements/message";

export type ChatMessage = {
    role: "user" | "assistant";
    content: string;
};

export default function Chat() {
    const [code, setCode] = useState("");
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [progress, setProgress] = useState(0);
    const [running, setRunning] = useState(false);
    const abortRef = useRef<AbortController | null>(null);

    const addMessage = (role: "user" | "assistant", content: string) => {
        setMessages((prev) => [...prev, { role, content }]);
    };

    const handleRun = async (codeStr: string) => {
        // Cancel any existing stream
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        setCode(codeStr);
        setRunning(true);
        setProgress(5);
        addMessage("user", codeStr);
        // Send to backend with mode=chat and empty query (initial analysis)
        try {
            await streamExplain(
                { code: codeStr, mode: "chat" },
                {
                    onChunk: (t) => {
                        // Append to the latest assistant message or start a new one
                        setMessages((prev) => {
                            const last = prev[prev.length - 1];
                            if (last && last.role === "assistant") {
                                last.content += t;
                                return [...prev.slice(0, -1), last];
                            }
                            return [...prev, { role: "assistant", content: t }];
                        });
                    },
                    onProgress: (p) => setProgress(p),
                    onError: (e) => console.error(e),
                    onDone: () => setRunning(false),
                },
                {
                    signal: abortRef.current.signal,
                    baseUrl:
                        process.env.NEXT_PUBLIC_BACKEND_URL ||
                        process.env.NEXT_PUBLIC_API_BASE_URL ||
                        "http://localhost:8000",
                }
            );
        } catch (e) {
            console.error(e);
        } finally {
            setRunning(false);
        }
    };

    const handleChat = async (query: string) => {
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        setRunning(true);
        setProgress(5);
        addMessage("user", query);
        try {
            await streamExplain(
                { code, mode: "chat", chat_query: query },
                {
                    onChunk: (t) => {
                        setMessages((prev) => {
                            const last = prev[prev.length - 1];
                            if (last && last.role === "assistant") {
                                last.content += t;
                                return [...prev.slice(0, -1), last];
                            }
                            return [...prev, { role: "assistant", content: t }];
                        });
                    },
                    onProgress: (p) => setProgress(p),
                    onError: (e) => console.error(e),
                    onDone: () => setRunning(false),
                },
                {
                    signal: abortRef.current.signal,
                    baseUrl:
                        process.env.NEXT_PUBLIC_BACKEND_URL ||
                        process.env.NEXT_PUBLIC_API_BASE_URL ||
                        "http://localhost:8000",
                }
            );
        } catch (e) {
            console.error(e);
        } finally {
            setRunning(false);
        }
    };

    return (
        <main style={{ maxWidth: 980, margin: "24px auto", padding: "0 16px" }}>
            <h1 style={{ fontSize: 22, marginBottom: 12 }}>Smart Multi‑Agent Chat</h1>
            <CodeEditor onRun={handleRun} disabled={running} />
            <ProgressBar value={progress} />
            <Conversation className="mt-4 max-h-[400px] overflow-y-auto" role="log">
                <ConversationContent>
                    {messages.length === 0 ? (
                        <ConversationEmptyState title="No messages yet" description="Run code or ask a question to start the conversation." />
                    ) : (
                        messages.map((msg, i) => (
                            <Message key={i} from={msg.role}>
                                <MessageContent>
                                    {msg.role === "assistant" ? (
                                        <MessageResponse>{msg.content}</MessageResponse>
                                    ) : (
                                        msg.content
                                    )}
                                </MessageContent>
                            </Message>
                        ))
                    )}
                </ConversationContent>
                <ConversationScrollButton />
                <MessageToolbar>
                    {/* Simple input for follow‑up queries */}
                    <input
                        type="text"
                        placeholder="Ask a follow‑up question..."
                        disabled={running}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && e.currentTarget.value.trim()) {
                                const q = e.currentTarget.value.trim();
                                e.currentTarget.value = "";
                                handleChat(q);
                            }
                        }}
                        style={{ width: "100%", padding: "8px" }}
                    />
                </MessageToolbar>
            </Conversation>
        </main>
    );
}
