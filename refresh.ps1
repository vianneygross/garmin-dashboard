# Récupère les données Garmin via le MCP, régénère data.js et ouvre le tableau de bord.
$ErrorActionPreference = 'Stop'
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
Start-Process (Join-Path $here 'index.html')
