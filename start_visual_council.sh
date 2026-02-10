
#!/bin/bash
echo "--- LAUNCHING IRON COUNCIL VISUAL LAYER ---"

# Trap to kill background processes on exit
trap 'kill $(jobs -p)' EXIT

# 0. Check for Environment Config
if [ ! -f ".env" ]; then
    echo "⚠️  No configuration found."
    python3 setup_env.py
fi

# 1. Start Backend
echo "[1/2] Starting FastAPI Server (Port 8000)..."

# Determine Python interpreter
if [ -f "./venv_stable/bin/python" ]; then
    PYTHON_CMD="./venv_stable/bin/python"
elif [ -f "./venv/bin/python" ]; then
    PYTHON_CMD="./venv/bin/python"
else
    PYTHON_CMD="python3"
fi

echo "Using Python: $PYTHON_CMD"
$PYTHON_CMD server.py &
BACKEND_PID=$!

# Wait for backend to be ready (naive check)
sleep 2

# 2. Start Frontend
echo "[2/2] Starting React Frontend (Port 5173)..."
cd ui
npm run dev -- --host &
FRONTEND_PID=$!

echo "--- SYSTEMS ONLINE ---"
echo "Open: http://localhost:5173"
echo "Press Ctrl+C to terminate both."

wait
