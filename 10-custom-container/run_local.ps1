# Run the SAME container on your laptop — no AWS, no SageMaker (Windows).
# Mounts the bundled sample data into the exact paths SageMaker would use.
#
#   .\run_local.ps1
param(
    [string]$Image = "roi-smdemo-custom-train:latest"
)
$ErrorActionPreference = "Stop"
$here = Split-Path $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force -Path "$here\local-output\model", "$here\local-output\output" | Out-Null

Write-Host "== running $Image locally, SageMaker-style paths ==" -ForegroundColor Cyan
Write-Host "   input : $here\sample-data        -> /opt/ml/input/data"
Write-Host "   model : $here\local-output\model -> /opt/ml/model"
docker run --rm `
    -v "${here}\sample-data:/opt/ml/input/data" `
    -v "${here}\local-output\model:/opt/ml/model" `
    -v "${here}\local-output\output:/opt/ml/output" `
    $Image train

Write-Host "`nTrained locally. Model artifact:" -ForegroundColor Green
Get-ChildItem "$here\local-output\model"
