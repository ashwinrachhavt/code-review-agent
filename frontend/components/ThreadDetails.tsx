"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";

type ThreadMessage = { role: string; content: string; created_at?: string };

type ThreadState = Record<string, any> & {
  security_report?: { vulnerabilities?: any[] };
  quality_report?: { metrics?: Record<string, any>; issues?: any[] };
  ast_report?: {
    files?: Array<{
      path?: string;
      language?: string;
      summary?: { functions?: any[]; classes?: any[]; imports?: any[] };
    }>;
    tree_sitter_findings?: any[];
  };
  context?: { total_files?: number; total_lines?: number; languages?: string[] };
  context_stats?: { disk_files?: number; disk_bytes?: number };
  tool_logs?: Array<{ id?: string; agent?: string; message?: string; status?: string }>;
  files?: Array<{ path?: string; size?: number; language?: string; content?: string }>;
};

export interface ThreadDetailsProps {
  thread: {
    thread_id: string;
    title?: string;
    report_text?: string;
    state?: ThreadState;
    messages?: ThreadMessage[];
    created_at?: string;
  } | null | undefined;
}

export default function ThreadDetails({ thread }: ThreadDetailsProps) {
  if (!thread || !thread.state) return null;

  const state = thread.state as ThreadState;
  const sec = state.security_report || {};
  const qual = state.quality_report || {};
  const ast = state.ast_report || {};
  const ctx = state.context || {};
  const ctxStats = state.context_stats || {};
  const logs = Array.isArray(state.tool_logs) ? state.tool_logs : [];
  const files = Array.isArray(state.files) ? state.files : [];

  return (
    <div className="space-y-3">
      <Tabs defaultValue="security" className="w-full">
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="quality">Quality</TabsTrigger>
          <TabsTrigger value="ast">AST</TabsTrigger>
          <TabsTrigger value="context">Context</TabsTrigger>
          <TabsTrigger value="tools">Tools</TabsTrigger>
          <TabsTrigger value="files">Files</TabsTrigger>
        </TabsList>

        <TabsContent value="security">
          <Section title="Security">
            {Array.isArray(sec.vulnerabilities) && sec.vulnerabilities.length > 0 ? (
              <ul className="list-disc ml-5 space-y-1">
                {sec.vulnerabilities.map((v: any, i: number) => (
                  <li key={i} className="text-sm">
                    {typeof v === 'string' ? v : JSON.stringify(v)}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>no vulnerabilities reported</Empty>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="quality">
          <Section title="Quality">
            {qual.metrics ? (
              <div className="text-sm grid grid-cols-3 gap-2">
                {Object.entries(qual.metrics).map(([k, v]) => (
                  <div key={k} className="rounded border p-2"><strong>{k}:</strong> {String(v)}</div>
                ))}
              </div>
            ) : null}
            <div className="mt-3" />
            {Array.isArray(qual.issues) && qual.issues.length > 0 ? (
              <ul className="list-disc ml-5 space-y-1">
                {qual.issues.map((it: any, i: number) => (
                  <li key={i} className="text-sm">
                    {typeof it === 'string' ? it : JSON.stringify(it)}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>no quality issues reported</Empty>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="ast">
          <Section title="AST">
            {Array.isArray(ast.files) && ast.files.length > 0 ? (
              <ScrollArea className="max-h-64">
                <div className="space-y-3">
                  {ast.files.map((f: any, i: number) => (
                    <div key={i} className="rounded border p-2">
                      <div className="text-sm font-medium">{f.path || '<unknown>'} {f.language ? `· ${f.language}` : ''}</div>
                      {f.summary && (
                        <div className="mt-2 text-xs grid grid-cols-3 gap-2">
                          <div>
                            <div className="font-semibold mb-1">Functions</div>
                            <ul className="list-disc ml-4">
                              {(f.summary.functions || []).slice(0, 10).map((fn: any, j: number) => (
                                <li key={j}>{typeof fn === 'string' ? fn : fn?.name || JSON.stringify(fn)}</li>
                              ))}
                            </ul>
                          </div>
                          <div>
                            <div className="font-semibold mb-1">Classes</div>
                            <ul className="list-disc ml-4">
                              {(f.summary.classes || []).slice(0, 10).map((cl: any, j: number) => (
                                <li key={j}>{typeof cl === 'string' ? cl : cl?.name || JSON.stringify(cl)}</li>
                              ))}
                            </ul>
                          </div>
                          <div>
                            <div className="font-semibold mb-1">Imports</div>
                            <ul className="list-disc ml-4">
                              {(f.summary.imports || []).slice(0, 10).map((imp: any, j: number) => (
                                <li key={j}>{String(imp)}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            ) : (
              <Empty>no AST data</Empty>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="context">
          <Section title="Context">
            <div className="text-sm grid grid-cols-3 gap-2">
              {ctx.total_files != null && <div className="rounded border p-2"><strong>Total files:</strong> {ctx.total_files}</div>}
              {ctx.total_lines != null && <div className="rounded border p-2"><strong>Total lines:</strong> {ctx.total_lines}</div>}
              {Array.isArray(ctx.languages) && (
                <div className="rounded border p-2"><strong>Languages:</strong> {ctx.languages.join(', ')}</div>
              )}
              {ctxStats.disk_files != null && <div className="rounded border p-2"><strong>Disk files:</strong> {ctxStats.disk_files}</div>}
              {ctxStats.disk_bytes != null && <div className="rounded border p-2"><strong>Disk bytes:</strong> {ctxStats.disk_bytes}</div>}
            </div>
          </Section>
        </TabsContent>

        <TabsContent value="tools">
          <Section title="Tool Logs">
            {logs.length ? (
              <ScrollArea className="max-h-64">
                <ul className="space-y-2">
                  {logs.map((l, i) => (
                    <li key={i} className="text-sm rounded border p-2">
                      <div className="font-medium">{l.agent || l.id || 'tool'}</div>
                      <div className="text-xs opacity-80">{l.status || 'completed'}</div>
                      <div className="mt-1 text-sm whitespace-pre-wrap">{l.message}</div>
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            ) : (
              <Empty>no tool logs</Empty>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="files">
          <Section title="Files">
            {files.length ? (
              <ScrollArea className="max-h-64">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left border-b">
                      <th className="py-1 pr-2">Path</th>
                      <th className="py-1 pr-2">Lang</th>
                      <th className="py-1 pr-2">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {files.slice(0, 200).map((f, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-1 pr-2 font-mono text-[12px]">{f.path || '<unknown>'}</td>
                        <td className="py-1 pr-2">{f.language || ''}</td>
                        <td className="py-1 pr-2">{f.size != null ? String(f.size) : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollArea>
            ) : (
              <Empty>no files recorded</Empty>
            )}
            <div className="mt-3">
              <details>
                <summary className="text-sm cursor-pointer">Raw state JSON</summary>
                <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-auto max-h-64">{JSON.stringify(state, null, 2)}</pre>
              </details>
            </div>
          </Section>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="font-semibold mb-2">{title}</div>
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-sm text-muted-foreground">{children}</div>;
}

