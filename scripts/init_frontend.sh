#!/usr/bin/env bash
set -e

# scripts/init_frontend.sh
# Khởi động Frontend Dev Server (Vite + React tại Port 5173)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/playground/frontend"
cd "$FRONTEND_DIR"

MAGENTA='\033[0;35m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${MAGENTA}==========================================================${NC}"
echo -e "${MAGENTA}   🎨 MCP SERVE REVERSE - FRONTEND DEV STUDIO            ${NC}"
echo -e "${MAGENTA}==========================================================${NC}"

# Kiểm tra node_modules
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${YELLOW}[*] Thư mục node_modules chưa có, đang tiến hành npm install...${NC}"
    npm install
fi

echo -e "${GREEN}[*] Đang khởi động Vite Dev Server...${NC}"
npm run dev "$@"
