"use client";

import { useState, useEffect } from "react";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "./ai-elements/conversation";
import {
  Message as AIMessage,
  MessageContent,
  MessageResponse,
  MessageActions,
  MessageAction,
} from "./ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
} from "./ai-elements/prompt-input";
import { CopyIcon, RefreshCcwIcon } from "lucide-react";

type Message = { role: "user" | "assistant"; content: string };

interface ChatbotUIProps {
  threadId: string | null;
  initialMessages?: Message[];
}

export default function ChatbotUI({ threadId, initialMessages = [] }: ChatbotUIProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setMessages(initialMessages);
  }, [initialMessages]);

  const refreshThread = async () => {
    if (!threadId) return;
    try {
      const res = await fetch(`/api/threads/${threadId}`);
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data?.messages)) {
        setMessages(data.messages as Message[]);
      }
    } catch {}
  };

  const regenerateLast = async () => {
    if (!messages.length || !threadId || isLoading) return;
    // Re-ask using the last user question if available; else do nothing
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    await handleSend(lastUser.content);
  };

  const handleSend = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || !threadId || isLoading) return;

    const userMessage: Message = { role: "user", content: trimmed };
    const historyToSend = [...messages, userMessage];

    setMessages((prev) => [...prev, userMessage, { role: "assistant", content: "" }]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          "x-thread-id": threadId,
        },
        body: JSON.stringify({ messages: historyToSend }),
      });

      if (!res.ok || !res.body) throw new Error("Chat request failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantContent = "";

      const processEvent = (evt: string) => {
        const dataLines = evt
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice(6));
        if (dataLines.length === 0) return;
        const payload = dataLines.join("\n");
        const trimmed = payload.trim();
        if (!trimmed) return;
        if (trimmed.startsWith(":::progress:")) return;
        if (trimmed === ":::done") {
          refreshThread();
          try {
            window.dispatchEvent(
              new CustomEvent("cra:thread-updated", { detail: { threadId } })
            );
          } catch {}
          return;
        }
        assistantContent += payload + "\n\n";
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") {
            last.content = assistantContent;
          }
          return next;
        });
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const evt of events) processEvent(evt);
      }
      if (buffer.trim()) processEvent(buffer);
    } catch {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant" && !last.content) {
          last.content = "[Error: Connection interrupted]";
        }
        return next;
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="border-b p-4">
        <h3 className="font-semibold">Chat</h3>
      </div>
      <div className="flex-1 p-2 overflow-hidden">
        <Conversation className="h-full">
          <ConversationContent>
            {messages.map((m, idx) => (
              <AIMessage key={idx} from={m.role}>
                <MessageContent>
                  <MessageResponse>{m.content}</MessageResponse>
                  {m.role === "assistant" && idx === messages.length - 1 && (
                    <MessageActions>
                      <MessageAction onClick={regenerateLast} label="Retry">
                        <RefreshCcwIcon className="size-3" />
                      </MessageAction>
                      <MessageAction
                        onClick={() => navigator.clipboard.writeText(m.content)}
                        label="Copy"
                      >
                        <CopyIcon className="size-3" />
                      </MessageAction>
                    </MessageActions>
                  )}
                </MessageContent>
              </AIMessage>
            ))}
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>
      </div>
      <div className="border-t p-2">
        <PromptInput
          onSubmit={(_, e) => {
            e.preventDefault();
            if (!input.trim()) return;
            handleSend(input);
          }}
          className="w-full"
        >
          <PromptInputBody>
            <PromptInputTextarea
              placeholder="Ask a question about the code..."
              disabled={isLoading || !threadId}
              onChange={(e) => setInput(e.target.value)}
              value={input}
            />
          </PromptInputBody>
          <PromptInputFooter />
        </PromptInput>
      </div>
    </div>
  );
}

