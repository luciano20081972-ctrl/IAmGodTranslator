$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

Write-Host "GodTranslator v10.3 local preview"
$dbUrlSecure = Read-Host "Paste DATABASE_URL" -AsSecureString
$dbUrlBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbUrlSecure)
$dbUrl = [Runtime.InteropServices.Marshal]::PtrToStringAuto($dbUrlBstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($dbUrlBstr)
if ([string]::IsNullOrWhiteSpace($dbUrl)) {
  throw "DATABASE_URL is required."
}
$adminPassword = Read-Host "Enter ADMIN_PASSWORD" -AsSecureString
$adminPasswordBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminPassword)
$adminPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($adminPasswordBstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($adminPasswordBstr)

$env:DATABASE_URL = $dbUrl
$env:DB_SCHEMA = "godtranslator_v10"
$env:ADMIN_PASSWORD = $adminPasswordPlain

$auth = Read-Host "Configure public Supabase Auth for this preview? y/N"
if ($auth -match "^(y|Y)") {
  $env:SUPABASE_URL = Read-Host "SUPABASE_URL"
  $env:SUPABASE_PUBLISHABLE_KEY = Read-Host "SUPABASE_PUBLISHABLE_KEY"
  $env:SUPABASE_AUTH_REDIRECT_URL = "http://127.0.0.1:8001/auth/callback"
  $env:AUTH_ENABLED = "true"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  throw "Python was not found on PATH. Install Python 3.12+ or activate the project virtual environment, then run this script again."
}

python --version
python -c "import fastapi, uvicorn, psycopg" | Out-Null
Write-Host "Starting GodTranslator at http://127.0.0.1:8001"
Write-Host "Press Ctrl+C to stop the preview server."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
