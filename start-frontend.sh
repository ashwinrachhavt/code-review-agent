#!/bin/bash

# Start frontend server
cd frontend

echo "🎨 Starting Code Review Agent Frontend..."
echo ""

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Start dev server
echo "Starting Next.js dev server on http://localhost:3000..."
npm run dev
