"use client";

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Send, Bot, User } from 'lucide-react';
import { Streamdown } from 'streamdown';

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
    const scrollRef = useRef<HTMLDivElement>(null);

    // Update messages when initialMessages changes (e.g. switching threads)
    useEffect(() => {
        setMessages(initialMessages);
    }, [initialMessages]);

    useEffect(() => {
        scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !threadId || isLoading) return;

        const userMessage: Message = { role: 'user', content: input };
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
                    messages: [{ role: 'user', content: input }],
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

            <ScrollArea className="flex-1 p-4">
                <div className="space-y-4">
                    {messages.length === 0 ? (
                        <div className="text-center text-muted-foreground py-8">
                            <p>Ask questions about the code review</p>
                            <p className="text-sm mt-2">
                                Example: "What security issues were found?"
                            </p>
                        </div>
                    ) : (
                        messages.map((message, index) => (
                            <div
                                key={index}
                                className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'
                                    }`}
                            >
                                {message.role === 'assistant' && (
                                    <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                                        <Bot className="w-4 h-4 text-primary-foreground" />
                                    </div>
                                )}
                                <div
                                    className={`rounded-lg p-3 max-w-[80%] ${message.role === 'user'
                                        ? 'bg-primary text-primary-foreground'
                                        : 'bg-muted'
                                        }`}
                                >
                                    {message.role === 'assistant' ? (
                                        <div className="prose prose-sm dark:prose-invert max-w-none">
                                            <Streamdown>{message.content}</Streamdown>
                                        </div>
                                    ) : (
                                        <p className="text-sm">{message.content}</p>
                                    )}
                                </div>
                                {message.role === 'user' && (
                                    <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0">
                                        <User className="w-4 h-4" />
                                    </div>
                                )}
                            </div>
                        ))
                    )}
                    <div ref={scrollRef} />
                </div>
            </ScrollArea>

            <form onSubmit={handleSubmit} className="border-t p-4">
                <div className="flex gap-2">
                    <Input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Ask a question about the code..."
                        disabled={isLoading}
                        className="flex-1"
                    />
                    <Button type="submit" disabled={!input.trim() || isLoading}>
                        <Send className="w-4 h-4" />
                    </Button>
                </div>
            </form>
        </div>
    );
}
