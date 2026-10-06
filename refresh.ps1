# Récupère les données Garmin via le MCP, régénère data.js et ouvre le tableau de bord.
param([switch]$Publish)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:Path += ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$ca = Join-Path $env:USERPROFILE '.garmin_ca.pem'
if (Test-Path $ca) { $env:SSL_CERT_FILE = $ca; $env:REQUESTS_CA_BUNDLE = $ca; $env:CURL_CA_BUNDLE = $ca }
$env:UV_SYSTEM_CERTS = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $here
uv run --python 3.12 --with mcp python fetch.py 2>$null
uv run --python 3.12 --with mcp python fetch_details.py 2>$null
uv run --python 3.12 python build.py
if ($Publish) {
  $env:GIT_TERMINAL_PROMPT = '0'
  git add data.js index.html
  git diff --cached --quiet
  if ($LASTEXITCODE -ne 0) { git commit -qm ("Mise a jour " + (Get-Date -Format 'yyyy-MM-dd HH:mm')); git push -q }
} else {
  Start-Process (Join-Path $here 'index.html')
}
