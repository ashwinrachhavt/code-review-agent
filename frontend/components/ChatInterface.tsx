"use client";

import { useState, useEffect } from 'react';
import { Send, Bot, User } from 'lucide-react';
import { Streamdown } from 'streamdown';
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "./ai-elements/conversation";
import {
  Message as AIMessage,
  MessageContent,
  MessageResponse,
} from "./ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
} from "./ai-elements/prompt-input";

interface Message {
    role: 'user' | 'assistant';
    content: string;
}

interface ChatInterfaceProps {
    threadId: string | null;
    initialMessages?: Message[];
}

export function ChatInterface({ threadId, initialMessages = [] }: ChatInterfaceProps) {
    const [messages, setMessages] = useState<Message[]>(initialMessages);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    // Update messages when initialMessages changes (e.g. switching threads)
    useEffect(() => {
        setMessages(initialMessages);
    }, [initialMessages]);

    // AI Elements provides ConversationScrollButton; no manual scroll needed here

    const handlePromptSubmit = async (
        _message: any,
        e: React.FormEvent<HTMLFormElement>
    ) => {
        e.preventDefault();
        const text = input.trim();
        if (!text || !threadId || isLoading) return;

        const userMessage: Message = { role: 'user', content: text };
        // Prepare full history (without assistant placeholder)
        const historyToSend = [...messages, userMessage];
        // Optimistically add the user message to UI
        setMessages((prev) => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);

        // Add placeholder for assistant message
        setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-thread-id': threadId,
                },
                body: JSON.stringify({
                    messages: historyToSend,
                }),
            });

            if (!response.ok) throw new Error('Chat request failed');

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            let assistantContent = '';

            if (reader) {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    assistantContent += chunk;

                    // Update the last message (assistant's placeholder)
                    setMessages((prev) => {
                        const newMessages = [...prev];
                        const lastMsg = newMessages[newMessages.length - 1];
                        if (lastMsg.role === 'assistant') {
                            lastMsg.content = assistantContent;
                        }
                        return newMessages;
                    });
                }
            }
        } catch (error) {
            console.error('Chat error:', error);
            // Remove the placeholder or show error
            setMessages((prev) => {
                const newMessages = [...prev];
                if (newMessages[newMessages.length - 1].role === 'assistant' && !newMessages[newMessages.length - 1].content) {
                    newMessages.pop(); // Remove empty placeholder if failed immediately
                    newMessages.push({
                        role: 'assistant',
                        content: 'Sorry, I encountered an error. Please try again.',
                    });
                } else {
                    newMessages.push({
                        role: 'assistant',
                        content: '\n\n[Error: Connection interrupted]',
                    });
                }
                return newMessages;
            });
        } finally {
            setIsLoading(false);
        }
    };

    if (!threadId) {
        return (
            <div className="flex items-center justify-center h-full text-muted-foreground">
                <div className="text-center space-y-2">
                    <Bot className="w-12 h-12 mx-auto opacity-50" />
                    <p>Analyze code first to start chatting</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            <div className="border-b p-4">
                <h3 className="font-semibold flex items-center gap-2">
                    <Bot className="w-5 h-5" />
                    Chat about your code
                </h3>
            </div>
            <div className="flex-1 p-2 overflow-hidden">
                <Conversation className="h-full">
                    <ConversationContent>
                        {messages.length === 0 ? (
                            <ConversationEmptyState
                                title="No messages yet"
                                description="Ask a question about the analysis to start."
                            />
                        ) : (
                            messages.map((m, idx) => (
                                <AIMessage key={idx} from={m.role}>
                                    <MessageContent>
                                        {m.role === 'assistant' ? (
                                            <MessageResponse>
                                                <div className="prose prose-sm dark:prose-invert max-w-none">
                                                    <Streamdown>{m.content}</Streamdown>
                                                </div>
                                            </MessageResponse>
                                        ) : (
                                            <div className="text-sm whitespace-pre-wrap">{m.content}</div>
                                        )}
                                    </MessageContent>
                                </AIMessage>
                            ))
                        )}
                    </ConversationContent>
                    <ConversationScrollButton />
                </Conversation>
            </div>
            <div className="border-t p-2">
                <PromptInput onSubmit={handlePromptSubmit} className="w-full">
                        <PromptInputBody>
                            <PromptInputTextarea
                                placeholder="Ask a question about the code..."
                                disabled={isLoading || !threadId}
                                onChange={(e) => setInput(e.target.value)}
                                value={input}
                            />
                        </PromptInputBody>
                        <PromptInputFooter>
                            <PromptInputSubmit disabled={!input.trim() || isLoading || !threadId} status={isLoading ? 'submitted' : 'idle'} />
                        </PromptInputFooter>
                    </PromptInput>
            </div>
        </div>
    );
}
