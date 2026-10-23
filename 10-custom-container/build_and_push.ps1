# Build the custom training image and push it to ECR (Windows / PowerShell).
# Teaching flow (run each step live): build -> ensure repo -> login -> tag -> push.
#
#   .\build_and_push.ps1
#   .\build_and_push.ps1 -Tag v1
#
# NOTE: Windows PowerShell 5.1 quirks handled here:
#  - docker writes progress to stderr, so we DON'T set ErrorActionPreference=Stop
#    (it would abort on normal output); we check $LASTEXITCODE instead.
#  - piping the ECR password to `docker login --password-stdin` corrupts it on 5.1,
#    so we pass it via -p (the standard reliable pattern on Windows).
param(
    [string]$Account = "029331796573",
    [string]$Region  = "us-east-1",
    [string]$Profile = "roitraining",
    [string]$Repo    = "roi-smdemo-custom-train",
    [string]$Tag     = "latest"
)
$ErrorActionPreference = "Continue"
$here     = Split-Path $MyInvocation.MyCommand.Path
$image    = "${Repo}:$Tag"
$ecr      = "$Account.dkr.ecr.$Region.amazonaws.com"
$ecrImage = "$ecr/$image"

function Assert-Ok($step) { if ($LASTEXITCODE -ne 0) { Write-Error "FAILED at: $step (exit $LASTEXITCODE)"; exit 1 } }

Write-Host "== 1/5 build image: $image ==" -ForegroundColor Cyan
& docker build -t $image "$here\container"
Assert-Ok "docker build"

Write-Host "== 2/5 ensure ECR repository exists: $Repo ==" -ForegroundColor Cyan
# create-repository errors if it already exists; that's fine, so swallow it.
& aws ecr create-repository --repository-name $Repo --profile $Profile --region $Region --output text 2>$null | Out-Null

Write-Host "== 3/5 authenticate Docker to ECR ==" -ForegroundColor Cyan
$pw = (& aws ecr get-login-password --region $Region --profile $Profile).Trim()
& docker login --username AWS --password $pw $ecr
Assert-Ok "docker login"

Write-Host "== 4/5 tag for ECR ==" -ForegroundColor Cyan
& docker tag $image $ecrImage
Assert-Ok "docker tag"

Write-Host "== 5/5 push to ECR ==" -ForegroundColor Cyan
& docker push $ecrImage
Assert-Ok "docker push"

Write-Host ""
Write-Host "DONE. Image now in ECR:" -ForegroundColor Green
Write-Host "  $ecrImage"
Write-Host "Run on SageMaker:  python launch_sagemaker_training.py --image-uri $ecrImage"
