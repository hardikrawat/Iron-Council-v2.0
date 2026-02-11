
#!/bin/bash
echo "--- LAUNCHING IRON COUNCIL VISUAL LAYER ---"

# Trap to kill background processes on exit
trap 'kill $(jobs -p)' EXIT

# Determine Python interpreter
if [ -f "./venv_stable/bin/python" ]; then
    PYTHON_CMD="./venv_stable/bin/python"
elif [ -f "./venv/bin/python" ]; then
    PYTHON_CMD="./venv/bin/python"
else
    PYTHON_CMD="python3"
fi

# 0. Check for Environment Config
if [ "$1" = "--reconfigure" ]; then
    echo "🔄 Reconfiguration requested..."
    $PYTHON_CMD setup_env.py --force
elif [ ! -f ".env" ]; then
    echo "⚠️  No configuration found."
    $PYTHON_CMD setup_env.py
fi

# 1. Start Backend
echo "[1/2] Starting FastAPI Server (Port 8000)..."
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
echo ""
echo "TIP: Run './start_visual_council.sh --reconfigure' to switch between Ollama and Cloud APIs."

wait
