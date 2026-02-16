#!/bin/bash

# --- IRON COUNCIL v2.0 LAUNCHER ---
# Enhanced startup script with developer tools

# Defaults
DO_KILL=false
DO_RESET=false
DO_OLLAMA_RESTART=false
DO_OPEN_BROWSER=false
DO_RECONFIGURE=false
DO_STOP=false

# ANSI Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Function: Show Help & Banner
# -----------------------------------------------------------------------------
show_help() {
    echo -e "${CYAN}"
    echo "██╗██████╗  ██████╗ ███╗   ███╗    ██████╗ ██████╗ ██╗   ██╗███╗   ██╗ ██████╗██╗██╗"
    echo "██║██╔══██╗██╔═══██╗████╗  ████║    ██╔════╝██╔═══██╗██║   ██║████╗  ██║██╔════╝██║██║"
    echo "██║██████╔╝██║   ██║██╔██╗ ██╔██║    ██║     ██║   ██║██║   ██║██╔██╗ ██║██║     ██║██║"
    echo "██║██╔══██╗██║   ██║██║╚██╗██║██║    ██║     ██║   ██║██║   ██║██║╚██╗██║██║     ██║██║"
    echo "██║██║  ██║╚██████╔╝██║ ╚████║██║    ╚██████╗╚██████╔╝╚██████╔╝██║ ╚████║╚██████╗██║███████╗"
    echo "╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝╚═╝╚══════╝"
    echo -e "${NC}"
    echo "Iron Council v2.0 - Autonomous Multi-Agent Simulation Engine"
    echo "Developer Edition (Hot Reload Enabled)"
    echo ""
    echo -e "${YELLOW}Usage: ./dev_start.sh [FLAGS]${NC}"
    echo ""
    echo "Flags:"
    echo "  -k, --kill            Force kill existing processes on ports 8000 (Backend) & 5173 (Frontend)."
    echo "  -r, --reset           Run factory reset (wipes memory/state) before starting."
    echo "  -o, --ollama-restart  Restart the Ollama service to ensure a fresh model state."
    echo "  -b, --open            Automatically open the UI in the default browser."
    echo "  -s, --stop            Kill all existing backend and frontend processes and exit."
    echo "  --turso-url           Update the Turso DB URL in .env."
    echo "  --turso-token         Update the Turso DB Token in .env."
    echo "  -h, --help            Show this help message."
    echo ""
    echo "Example:"
    echo "  ./dev_start.sh --kill --reset --open"
    echo "  ./dev_start.sh --turso-url=https://xyz.turso.io --turso-token=... "
    echo ""
}

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

# -----------------------------------------------------------------------------
# Argument Parsing
# -----------------------------------------------------------------------------
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -k|--kill) DO_KILL=true ;;
        -r|--reset) DO_RESET=true ;;
        -o|--ollama-restart) DO_OLLAMA_RESTART=true ;;
        -b|--open) DO_OPEN_BROWSER=true ;;
        -s|--stop) DO_STOP=true ;;
        --reconfigure) DO_RECONFIGURE=true ;;
        --turso-url=*) 
            TURSO_URL="${1#*=}"
            if [[ "$TURSO_URL" == libsql://* ]]; then
                TURSO_URL="${TURSO_URL/libsql:\/\//https:\/\/}"
            fi
            $PYTHON_CMD -c "
import os
val = \"$TURSO_URL\"
lines = open('.env').readlines() if os.path.exists('.env') else []
if lines and not lines[-1].endswith('\n'): lines[-1] += '\n'
new_lines = []
found = False
for line in lines:
    if line.startswith('TURSO_DB_URL='):
        new_lines.append(f'TURSO_DB_URL={val}\n')
        found = True
    else:
        new_lines.append(line)
if not found:
    new_lines.append(f'TURSO_DB_URL={val}\n')
with open('.env', 'w') as f:
    f.writelines(new_lines)
"
            echo -e "${GREEN}✔ Updated TURSO_DB_URL in .env${NC}"
            ;;
        --turso-token=*)
            TURSO_TOKEN="${1#*=}"
            $PYTHON_CMD -c "
import os
val = \"$TURSO_TOKEN\"
lines = open('.env').readlines() if os.path.exists('.env') else []
if lines and not lines[-1].endswith('\n'): lines[-1] += '\n'
new_lines = []
found = False
for line in lines:
    if line.startswith('TURSO_DB_TOKEN='):
        new_lines.append(f'TURSO_DB_TOKEN={val}\n')
        found = True
    else:
        new_lines.append(line)
if not found:
    new_lines.append(f'TURSO_DB_TOKEN={val}\n')
with open('.env', 'w') as f:
    f.writelines(new_lines)
"
            echo -e "${GREEN}✔ Updated TURSO_DB_TOKEN in .env${NC}"
            ;;
        -h|--help) show_help; exit 0 ;;
        *) echo "Unknown parameter passed: $1"; show_help; exit 1 ;;
    esac
    shift
done


echo -e "${BLUE}--- IRON COUNCIL SYSTEM INITIALIZATION ---${NC}"

# -----------------------------------------------------------------------------
# 1. Pre-flight Checks & Actions
# -----------------------------------------------------------------------------

# Kill Ports (if requested)
if [ "$DO_KILL" = true ]; then
    echo -e "${YELLOW}[ACTION] Killing existing processes on Ports 8000 & 5173...${NC}"
    lsof -t -i:8000 | xargs kill -9 2>/dev/null
    lsof -t -i:5173 | xargs kill -9 2>/dev/null
    echo -e "${GREEN}✔ Cleared ports.${NC}"
fi

# Ollama Restart (if requested)
if [ "$DO_OLLAMA_RESTART" = true ]; then
    echo -e "${YELLOW}[ACTION] Restarting Ollama Service...${NC}"
    pkill -x ollama 2>/dev/null
    sleep 1
    ollama serve >/dev/null 2>&1 &
    echo -e "${GREEN}✔ Ollama restarted in background.${NC}"
    sleep 2 # warm up
elif ! pgrep -x "ollama" > /dev/null; then
    # Auto-start if not running, even without flag
    echo -e "${YELLOW}[NOTICE] Ollama not found. Starting service...${NC}"
    ollama serve >/dev/null 2>&1 &
    sleep 2
fi

# Configuration Check
if [ "$DO_RECONFIGURE" = true ]; then
    echo "🔄 Reconfiguration requested..."
    $PYTHON_CMD setup_env.py --force
elif [ ! -f ".env" ]; then
    echo "⚠️  No configuration found."
    $PYTHON_CMD setup_env.py
fi

# Reset (if requested)
if [ "$DO_RESET" = true ]; then
    echo -e "${RED}[ACTION] Triggering Factory Reset...${NC}"
    # Use 'echo y' to pipe 'yes' to the reset script prompts? 
    # The reset script asks "Wipe all memories (Vector DB)? (y/n)".
    # If we want it interactive, we just run it. If we want fully automated, we might need to pipe.
    # Let's keep it interactive for safety as per plan, but inform user.
    $PYTHON_CMD reset.py
    echo -e "${GREEN}✔ Reset procedure completed.${NC}"
fi

# -----------------------------------------------------------------------------
# 2. Dependency Checks
# -----------------------------------------------------------------------------

# Frontend Dependency Check
if [ ! -d "ui/node_modules" ]; then
    echo -e "${RED}⚠️  CRITICAL ERROR: Frontend dependencies not found!${NC}"
    echo -e "${YELLOW}The 'ui/node_modules' directory is missing, which is required for the Visual Council.${NC}"
    echo ""
    echo -e "To resolve this manually, run:"
    echo -e "  ${CYAN}cd ui && npm install${NC}"
    echo ""
    echo -e "Would you like to install them automatically now? (y/n)"
    
    # Check if terminal is interactive
    if [ -t 0 ]; then
        read -r -p "> " install_choice
        if [[ "$install_choice" =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}[ACTION] Installing frontend dependencies...${NC}"
            (cd ui && npm install)
            echo -e "${GREEN}✔ Dependencies installed. Resuming startup...${NC}"
        else
            echo -e "${RED}Aborting startup. Please install dependencies manually.${NC}"
            exit 1
        fi
    else
        echo -e "${RED}Non-interactive shell detected. Cannot prompt for installation.${NC}"
        echo -e "${YELLOW}Please run 'cd ui && npm install' before starting.${NC}"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# 3. Main Startup
# -----------------------------------------------------------------------------

echo "[1/2] Starting FastAPI Server (Port 8000)..."
$PYTHON_CMD server.py &
BACKEND_PID=$!

# Wait for backend to be ready (naive check)
sleep 2

echo "[2/2] Starting React Frontend (Port 5173)..."
cd ui
npm run dev -- --host &
FRONTEND_PID=$!
cd ..

# -----------------------------------------------------------------------------
# 3. Post-Startup Actions
# -----------------------------------------------------------------------------

if [ "$DO_OPEN_BROWSER" = true ]; then
    echo -e "${GREEN}[ACTION] Opening Browser...${NC}"
    # Sleep a bit to ensure vite is up
    sleep 3
    open "http://localhost:5173"
fi

echo ""
echo -e "${GREEN}--- SYSTEMS ONLINE ---${NC}"
echo "Open: http://localhost:5173"
echo "Press Ctrl+C to terminate both."
echo ""

wait
