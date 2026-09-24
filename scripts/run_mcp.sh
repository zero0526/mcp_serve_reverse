#!/usr/bin/env bash
set -e

# scripts/run_mcp.sh
# Khởi động MCP Server giao thức stdio (dành cho Cursor / Claude Desktop / Antigravity kết nối)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Kiểm tra Virtual Environment
VENV_PYTHON=""
if [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif [ -f "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    VENV_PYTHON="$PROJECT_ROOT/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    VENV_PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    VENV_PYTHON="python"
fi

echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}   🧠 MCP SERVER - MODEL CONTEXT PROTOCOL (STDIO)         ${NC}"
echo -e "${GREEN}==========================================================${NC}"
echo -e "${CYAN}[*] Đang khởi chạy MCP Server...${NC}"

exec "$VENV_PYTHON" -m app.main run-mcp --transport stdio "$@"
