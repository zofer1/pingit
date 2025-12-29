#!/usr/bin/env powershell
<#
.SYNOPSIS
    Run the PingIT WebServer comprehensive test suite

.DESCRIPTION
    Automatically activates virtual environment and runs test_webserver.py
    with proper error handling and colored output

.EXAMPLE
    .\run_tests.ps1

.NOTES
    Requires virtual environment at .\.venv
#>

param(
    [switch]$Help,
    [switch]$Verbose,
    [switch]$Quick = $false,
    [switch]$CleanupOnly = $false
)

# Color output helper
function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "╔" + ("═" * 78) + "╗" -ForegroundColor Cyan
    Write-Host "║ $($Message.PadRight(76)) ║" -ForegroundColor Cyan
    Write-Host "╚" + ("═" * 78) + "╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ️  $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠️  $Message" -ForegroundColor Yellow
}

function Show-Help {
    @"
PingIT WebServer Test Suite Runner

USAGE:
    .\run_tests.ps1 [OPTIONS]

OPTIONS:
    -Help              Show this help message
    -Verbose           Show detailed output
    -Quick             Skip data generation, use existing DB
    -CleanupOnly       Clean up test files and exit
    
EXAMPLES:
    .\run_tests.ps1                    # Run full test suite
    .\run_tests.ps1 -Quick             # Quick test (reuse existing data)
    .\run_tests.ps1 -CleanupOnly       # Clean up and exit
    .\run_tests.ps1 -Verbose           # Detailed output
    
QUICK START:
    1. Open PowerShell
    2. Navigate to project directory
    3. Run: .\run_tests.ps1
    4. Wait for completion (~45 seconds)
    5. Check console for results
    
For full documentation, see TEST_README.md or TEST_QUICK_START.md
"@
}

# Show help if requested
if ($Help) {
    Show-Help
    exit 0
}

Write-Header "PingIT WebServer Test Suite Runner"

# Check if already in project directory
$projectDir = Get-Location
if (-not (Test-Path "webserver.py")) {
    Write-Error "webserver.py not found in current directory"
    Write-Info "Please run this script from the PingIT project root directory"
    exit 1
}

# Cleanup function
function Cleanup-TestFiles {
    Write-Info "Cleaning up test files..."
    
    $files_to_remove = @(
        "pingit_test.db",
        "webserver-*.log"
    )
    
    foreach ($pattern in $files_to_remove) {
        $items = Get-Item $pattern -ErrorAction SilentlyContinue
        if ($items) {
            foreach ($item in $items) {
                try {
                    Remove-Item $item -Force
                    Write-Success "Removed: $($item.Name)"
                } catch {
                    Write-Warning "Could not remove: $($item.Name)"
                }
            }
        }
    }
}

# Cleanup if requested
if ($CleanupOnly) {
    Cleanup-TestFiles
    Write-Success "Cleanup complete"
    exit 0
}

# Check for virtual environment
if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Error "Virtual environment not found at .\.venv"
    Write-Info "Creating virtual environment..."
    
    try {
        python -m venv .venv
        Write-Success "Virtual environment created"
    } catch {
        Write-Error "Failed to create virtual environment: $_"
        exit 1
    }
}

# Activate virtual environment
Write-Info "Activating virtual environment..."
try {
    & ".\.venv\Scripts\Activate.ps1"
    Write-Success "Virtual environment activated"
} catch {
    Write-Error "Failed to activate virtual environment: $_"
    exit 1
}

# Check Python version
Write-Info "Checking Python version..."
try {
    $pythonVersion = python --version 2>&1
    Write-Success "Using $pythonVersion"
} catch {
    Write-Error "Python not found: $_"
    exit 1
}

# Install/update requirements
Write-Info "Checking dependencies..."
try {
    pip install -q -r requirements.txt
    Write-Success "Dependencies available"
} catch {
    Write-Warning "Could not update dependencies: $_"
}

# Cleanup old test files if not in quick mode
if (-not $Quick) {
    Cleanup-TestFiles
}

# Run tests
Write-Header "Starting Tests"

if ($Verbose) {
    # Run with verbose output
    python test_webserver.py
} else {
    # Run normally
    python test_webserver.py
}

$exitCode = $LASTEXITCODE

Write-Header "Test Run Complete"

if ($exitCode -eq 0) {
    Write-Success "All tests passed! ✓"
} else {
    Write-Error "Some tests failed. See output above for details."
}

# Final cleanup prompt
Write-Info "Run '.\run_tests.ps1 -CleanupOnly' to remove test files"

exit $exitCode

