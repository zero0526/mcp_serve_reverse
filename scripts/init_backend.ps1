# scripts/init_backend.ps1
# Khởi động Backend API Server (Starlette ASGI trên Port 8000)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   🚀 MCP SERVE REVERSE - BACKEND STUDIO SERVER           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Kiểm tra Virtual Environment
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = "python"
    Write-Host "[!] .venv cục bộ không tìm thấy, sử dụng Python hệ thống." -ForegroundColor Yellow
} else {
    Write-Host "[+] Sử dụng Virtual Environment: $VenvPython" -ForegroundColor Green
}

# Chạy backend server
Write-Host "[*] Đang khởi động Backend REST API tại http://127.0.0.1:8000 ..." -ForegroundColor Green
& $VenvPython -m playground.backend.main
