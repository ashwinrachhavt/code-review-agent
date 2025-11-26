#!/usr/bin/env bash

set -euo pipefail

# End-to-end test: Frontend -> Backend streaming via /api/review

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  set +e
  if [[ -n "$FRONTEND_PID" ]] && ps -p "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "Stopping frontend (pid=$FRONTEND_PID)…"
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$BACKEND_PID" ]] && ps -p "$BACKEND_PID" >/dev/null 2>&1; then
    echo "Stopping backend (pid=$BACKEND_PID)…"
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  local max_wait="${2:-60}"
  local t=0
  until curl -fsS "$url" >/dev/null 2>&1; do
    sleep 1
    t=$((t+1))
    if [[ "$t" -ge "$max_wait" ]]; then
      echo "Timed out waiting for $url" >&2
      return 1
    fi
  done
}

echo "Checking prerequisites…"
require_cmd python3
require_cmd uvicorn
require_cmd curl
require_cmd pnpm

echo "Installing backend (editable)…"
python3 -m pip install -e "$ROOT_DIR/backend" >/dev/null

echo "Installing frontend dependencies (pnpm)…"
(
  cd "$ROOT_DIR/frontend"
  pnpm install >/dev/null
)

echo "Starting backend (FastAPI + LangGraph)…"
(
  cd "$ROOT_DIR"
  # Disable checkpointer by default for e2e simplicity; set LANGGRAPH_CHECKPOINTER=1 + REDIS_URL to enable
  LANGGRAPH_CHECKPOINTER=0 uvicorn backend.main:app --port 8000 --log-level warning &
  echo $! > .backend.pid
) 
BACKEND_PID="$(cat "$ROOT_DIR/.backend.pid" 2>/dev/null || echo "")"

echo "Waiting for backend health…"
wait_for_http "$BACKEND_URL/health" 60
echo "Backend is up at $BACKEND_URL"

echo "Starting frontend (Next.js dev)…"
(
  cd "$ROOT_DIR/frontend"
  NEXT_PUBLIC_BACKEND_URL="$BACKEND_URL" pnpm dev -- -p 3000 >/dev/null 2>&1 &
  echo $! > "$ROOT_DIR/.frontend.pid"
)
FRONTEND_PID="$(cat "$ROOT_DIR/.frontend.pid" 2>/dev/null || echo "")"

echo "Waiting for frontend…"
wait_for_http "$FRONTEND_URL" 120
echo "Frontend is up at $FRONTEND_URL"

echo "Running streaming request via frontend /api/review…"
REQ_PAYLOAD='{"id":"e2e-thread","messages":[{"role":"user","content":"Quick check: what did the review find?"}]}'
OUT_FILE="$ROOT_DIR/.e2e_stream.txt"
rm -f "$OUT_FILE"

set +e
curl -sS -N --max-time 90 \
  -H 'Content-Type: application/json' \
  -d "$REQ_PAYLOAD" \
  "$FRONTEND_URL/api/review" | tee "$OUT_FILE"
STATUS=$?
set -e

if [[ "$STATUS" -ne 0 ]]; then
  echo "Request failed with status $STATUS" >&2
  exit 1
fi

if [[ ! -s "$OUT_FILE" ]]; then
  echo "No output received from streaming endpoint" >&2
  exit 1
fi

echo
echo "E2E success: received $(wc -c < "$OUT_FILE") bytes from frontend -> backend stream."
echo "Sample output (first 200 bytes):"
head -c 200 "$OUT_FILE"; echo

exit 0
