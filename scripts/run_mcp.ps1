# scripts/run_mcp.ps1
# Khởi động MCP Server giao thức stdio (dành cho Cursor / Claude Desktop / Antigravity kết nối)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = "python"
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   🧠 MCP SERVER - MODEL CONTEXT PROTOCOL (STDIO)         " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "[*] Đang khởi chạy MCP Server..." -ForegroundColor Cyan

& $VenvPython -m app.main run-mcp --transport stdio
