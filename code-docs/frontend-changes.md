Frontend Integration Notes

Goal: Align the frontend with the new backend architecture (context node, threads persistence, slim routes) and enable folder uploads (files modality) alongside pasted code.

1) Endpoints and Proxies
- Replace legacy history endpoint usage:
  - Remove calls to `GET /explain/history`.
  - Add proxies and callers for new endpoints:
    - `GET /threads` → list recent threads for sidebar.
    - `GET /threads/{id}` → fetch a thread with `state` and `messages`.

- Add Next.js API proxies:
  - `frontend/app/api/threads/route.ts` (GET):
    - Proxies to `${BACKEND_URL}/threads?limit=50`.
  - `frontend/app/api/threads/[id]/route.ts` (GET):
    - Proxies to `${BACKEND_URL}/threads/${id}`.

2) Streaming Behavior (SSE)
- Existing SSE parsing is compatible. Keep reading `data:`-prefixed lines and continue parsing `:::progress: N` markers.
- New optional stream message: `📚 Context ready.` can be displayed in the chat transcript as a brief status.
- Continue displaying:
  - `🔎 Router: language detection done.`
  - `🧪 Tools complete.`
- No change needed in `frontend/lib/streamingClient.ts` except optional UI for the context-ready line.

3) /explain payloads and thread id header
- Pasted code (unchanged):
  - Body includes `{ code, mode?, agents?, thread_id? }`.
- Folder modality (new):
  - Body includes `{ files: [{ path, content }...], source: "folder", mode?, agents?, thread_id? }`.
  - The backend will infer language and build context.
- Ensure the proxy sets and forwards `x-thread-id`:
  - Request header: set `x-thread-id` when a thread is present.
  - Response header from backend includes `x-thread-id`; capture and expose this header so the frontend state can store the live `threadId`.

Modify `frontend/app/api/review/route.ts`:
- Include `files` and `source` keys when present (wire your UI state to pass them):
  ```ts
  const body: any = { messages, thread_id: id, agents, mode: forcedMode, code, entry };
  if (Array.isArray(files) && files.length) {
    body.files = files.map(f => ({ path: f.path, content: f.content }));
    body.source = 'folder';
  }
  ```
- Forward thread id header from backend:
  ```ts
  const threadHeader = res.headers.get('x-thread-id');
  const responseHeaders: Record<string, string> = {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': 'no-cache',
  };
  if (threadHeader) responseHeaders['x-thread-id'] = threadHeader;
  return new Response(stream, { headers: responseHeaders });
  ```

4) Chat endpoint
- No body/stream changes necessary.
- Persisted assistant replies are handled server-side; if the UI needs to reflect them immediately, call `GET /threads/{id}` after a chat turn to refresh messages.

5) Sidebar: list and open threads
- Update the sidebar to use:
  - `GET /api/threads` → list threads: `[{ id, created_at, title, message_count }]`.
  - `GET /api/threads/{id}` → returns `{ id, created_at, title, state, report_text, messages }`.
- Replace any usage of `/api/history` with the new threads endpoints.

6) Folder upload UI (new)
- Add a file-picker or drag‑and‑drop panel that collects project files. Filter to scannable types client‑side if desired (`.py, .js, .ts, .tsx, .jsx, .java`).
- Read file contents and send to `/api/review` with the `files` array and `source: 'folder'`.
- For very large folders, consider sampling or paging in the UI.

7) Environment variables
- The frontend already uses `NEXT_PUBLIC_BACKEND_URL` (preferred) or `NEXT_PUBLIC_API_BASE_URL`.
- No additional changes required.

8) Optional UI niceties
- Display the context summary (languages, total files/lines) when `📚 Context ready.` arrives by calling `GET /api/threads/{id}` after analysis completes (or parse from stream once final report is received, since state is persisted at the end of /explain).
- Show progress bar using `:::progress: N` markers (already implemented).

