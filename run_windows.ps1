# ===============================================================================
#     ANG AUTOMOTIVE - BMW M-PERFORMANCE TELEMATICS & REMOTE ECU TUNING
#       ISO 13400 DoIP / ISO 14229 UDS Platform for Windows PowerShell
# ===============================================================================

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "    ANG AUTOMOTIVE - BMW M-PERFORMANCE TELEMATICS & REMOTE ECU TUNING" -ForegroundColor White
Write-Host "      ISO 13400 DoIP / ISO 14229 UDS Platform for Bosch MEVD17, MSD80, MG1" -ForegroundColor Yellow
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Locate Python
$pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py.exe -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Host "[ERROR] Python is not found in your Windows PATH!" -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from https://www.python.org/downloads/ (Check 'Add Python to PATH')" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    Exit 1
}

Write-Host "[1/4] Found Python interpreter: $($pythonCmd.Source)" -ForegroundColor Green
& $pythonCmd.Source --version

# 2. Setup Virtual Environment
$venvPath = Join-Path $PSScriptRoot "venv"
$venvActivate = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $venvActivate)) {
    Write-Host "[2/4] Creating virtual environment at $venvPath..." -ForegroundColor Cyan
    & $pythonCmd.Source -m venv $venvPath
} else {
    Write-Host "[2/4] Virtual environment detected." -ForegroundColor Green
}

# Activate Venv
& $venvActivate

# 3. Install Requirements
Write-Host "[3/4] Installing / Verifying dependencies from requirements.txt..." -ForegroundColor Cyan
python -m pip install --upgrade pip --quiet
python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") --quiet

# 4. Start Server
Write-Host "[4/4] Launching ANG Automotive Platform..." -ForegroundColor Green
Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  Platform Active:" -ForegroundColor White
Write-Host "    - Web Dashboard: http://localhost:5000" -ForegroundColor Yellow
Write-Host "    - DoIP Gateway:  Port 13400 (TCP / UDP)" -ForegroundColor Yellow
Write-Host "  Opening default browser..." -ForegroundColor Gray
Write-Host "  Press CTRL+C to terminate." -ForegroundColor Gray
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""

# Open browser asynchronously
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:5000"
} | Out-Null

# Start Flask App
python (Join-Path $PSScriptRoot "app.py")
