# scripts/init_frontend.ps1
# Khởi động Frontend Dev Server (Vite + React tại Port 5173)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$FrontendDir = Join-Path $ProjectRoot "playground\frontend"
Set-Location $FrontendDir

Write-Host "==========================================================" -ForegroundColor Magenta
Write-Host "   🎨 MCP SERVE REVERSE - FRONTEND DEV STUDIO            " -ForegroundColor Magenta
Write-Host "==========================================================" -ForegroundColor Magenta

# Kiểm tra node_modules
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "[*] Thư mục node_modules chưa có, đang tiến hành npm install..." -ForegroundColor Yellow
    npm install
}

Write-Host "[*] Đang khởi động Vite Dev Server..." -ForegroundColor Green
npm run dev
