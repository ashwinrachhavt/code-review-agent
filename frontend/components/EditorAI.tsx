"use client";

import { useEffect, useState } from "react";
// Lightweight client-side streaming for /api/editor
async function streamEditor(prompt: string, onText: (chunk: string) => void) {
  const res = await fetch('/api/editor', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  if (!res.body) throw new Error('No response body');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    if (buffer) {
      onText(buffer);
      buffer = '';
    }
  }
}

type Props = { initialContent?: string };

function buildPrompt(kind: string, text: string) {
  switch (kind) {
    case "summarize":
      return `Summarize the following content in concise bullet points.\n\n${text}`;
    case "rewrite":
      return `Rewrite the following content for clarity and brevity while preserving meaning. Return Markdown only.\n\n${text}`;
    case "bulletize":
      return `Convert the following content into a clean Markdown list of bullets with short, actionable lines.\n\n${text}`;
    case "fix":
      return `Fix grammar and flow for the following content, keeping technical details intact.\n\n${text}`;
    default:
      return text;
  }
}

// Inner TipTap-powered editor rendered only when modules are available
function EditorAIInner({ initialContent }: Props & {
  modules: any;
}) {
  const { EditorContent, useEditor, StarterKit, Placeholder } = (window as any).__tiptap as any || {};
  const [activeKind, setActiveKind] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder: 'Refine the report here. Select text and choose an AI action.' }),
    ],
    content: initialContent || '',
  });

  useEffect(() => {
    if (editor && initialContent && editor.isEmpty) {
      editor.commands.setContent(initialContent);
    }
  }, [editor, initialContent]);

  async function run(kind: string) {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    const selected = editor.state.doc.textBetween(from, to, '\n\n');
    const base = selected || editor.getText();
    const prompt = buildPrompt(kind, base);
    setActiveKind(kind);
    setDraft('');
    setIsLoading(true);
    try {
      await streamEditor(prompt, (chunk) => setDraft((d) => d + chunk));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!editor) return;
    if (!isLoading && draft && activeKind) {
      const { from, to } = editor.state.selection;
      const text = draft;
      if (from !== to) {
        editor.chain().focus().insertContentAt({ from, to }, text).run();
      } else {
        editor.chain().focus().insertContent(`\n\n${text}`).run();
      }
      setActiveKind(null);
      setDraft('');
    }
  }, [draft, isLoading, editor, activeKind]);

  const disabled = !editor || isLoading;

  return (
    <div className="mt-6 rounded border">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="text-sm font-medium">AI Editor</div>
        <div className="flex gap-2">
          <button className="rounded bg-gray-100 px-2 py-1 text-xs hover:bg-gray-200" onClick={() => run('summarize')} disabled={disabled}>Summarize</button>
          <button className="rounded bg-gray-100 px-2 py-1 text-xs hover:bg-gray-200" onClick={() => run('rewrite')} disabled={disabled}>Rewrite</button>
          <button className="rounded bg-gray-100 px-2 py-1 text-xs hover:bg-gray-200" onClick={() => run('bulletize')} disabled={disabled}>Bulletize</button>
          <button className="rounded bg-gray-100 px-2 py-1 text-xs hover:bg-gray-200" onClick={() => run('fix')} disabled={disabled}>Fix Grammar</button>
        </div>
      </div>
      <div className="prose max-w-none px-4 py-3">
        <EditorContent editor={editor} />
      </div>
      {isLoading && (
        <div className="px-4 pb-3 text-xs text-gray-500">AI is writing…</div>
      )}
    </div>
  );
}

export default function EditorAI({ initialContent }: Props) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [reactMod, kitMod, phMod] = await Promise.all([
          import("@tiptap/react"),
          import("@tiptap/starter-kit"),
          import("@tiptap/extension-placeholder"),
        ]);
        (window as any).__tiptap = {
          EditorContent: reactMod.EditorContent,
          useEditor: reactMod.useEditor,
          StarterKit: kitMod.default,
          Placeholder: phMod.default,
        };
        setLoaded(true);
      } catch (e) {
        console.error("TipTap modules failed to load:", e);
        setFailed(true);
      }
    })();
  }, []);

  if (failed) {
    return null; // graceful no-op if TipTap not available
  }
  if (!loaded) {
    return (
      <div className="mt-6 rounded border px-4 py-3 text-xs text-gray-500">Loading editor…</div>
    );
  }
  return <EditorAIInner initialContent={initialContent} modules={(window as any).__tiptap} />;
}
