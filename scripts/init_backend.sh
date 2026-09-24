#!/usr/bin/env bash
set -e

# scripts/init_backend.sh
# Khởi động Backend API Server (Starlette ASGI trên Port 8000)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${CYAN}==========================================================${NC}"
echo -e "${CYAN}   🚀 MCP SERVE REVERSE - BACKEND STUDIO SERVER           ${NC}"
echo -e "${CYAN}==========================================================${NC}"

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

if [[ "$VENV_PYTHON" == *".venv"* ]]; then
    echo -e "${GREEN}[+] Sử dụng Virtual Environment: $VENV_PYTHON${NC}"
else
    echo -e "${YELLOW}[!] .venv cục bộ không tìm thấy, sử dụng Python hệ thống: $VENV_PYTHON${NC}"
fi

# Chạy backend server
echo -e "${GREEN}[*] Đang khởi động Backend REST API tại http://127.0.0.1:8000 ...${NC}"
exec "$VENV_PYTHON" -m playground.backend.main "$@"
