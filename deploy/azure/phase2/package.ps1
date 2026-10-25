# Build only. No Azure login or deployment. Use Windows SDK 10.0.402.
param([string]$Output = "$env:TEMP\router-release")
$ErrorActionPreference = 'Stop'
if (Test-Path $Output) { throw 'Output already exists; choose an empty output directory' }
New-Item -ItemType Directory $Output | Out-Null
$publish = Join-Path $Output 'publish'
dotnet publish src/dotnet/Router.Functions -c Release -o $publish --self-contained false
if ($LASTEXITCODE -ne 0) { throw 'Functions publish failed' }
New-Item -ItemType Directory (Join-Path $publish 'tools') | Out-Null
New-Item -ItemType Directory (Join-Path $publish 'policies') | Out-Null
$opa = Join-Path $publish 'tools/opa.exe'
Invoke-WebRequest 'https://github.com/open-policy-agent/opa/releases/download/v1.9.0/opa_windows_amd64.exe' -OutFile $opa
if ((Get-FileHash $opa -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'ea07eb413f7d0b258dc2e45d054ebb7df6fad42ad436bbe96e5dc6d5e7bc2951') { throw 'OPA digest mismatch' }
Copy-Item policies/capabilities.json (Join-Path $publish 'policies/capabilities.json')
foreach ($required in @('host.json','functions.metadata','worker.config.json','Router.Functions.dll','tools/opa.exe','policies/capabilities.json')) {
 if (!(Test-Path (Join-Path $publish $required))) { throw "Missing package file: $required" }
}
if (Get-ChildItem $publish -Recurse -Filter local.settings.json) { throw 'Local settings must not be packaged' }
Compress-Archive -Path (Join-Path $publish '*') -DestinationPath (Join-Path $Output 'router.zip')
Get-FileHash (Join-Path $Output 'router.zip') -Algorithm SHA256
