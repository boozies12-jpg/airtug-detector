#!/bin/bash
set -e

echo "Starting Backend API server on port 41730..."
python3 -m uvicorn src.api.server:app --host 0.0.0.0 --port 41730 &
BACKEND_PID=$!

echo "Starting Vite Frontend dev server on port 41732..."
npx vite --port 41732 --host 0.0.0.0 &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

wait
