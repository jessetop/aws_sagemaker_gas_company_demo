# Tear down all resources created by the SageMaker Unified Studio demo series.
# Safe to re-run. Only touches resources named/tagged for this demo.
#
#   powershell -File cleanup/cleanup.ps1                 # jobs/apps/endpoints, keep bucket+role
#   powershell -File cleanup/cleanup.ps1 -IncludeBucket  # also empty + delete the S3 bucket
#   powershell -File cleanup/cleanup.ps1 -IncludeRole    # also delete the shared IAM role
#
# Invoked as `powershell`, not `pwsh`: PowerShell 7 is not installed on the
# authoring machine, and `pwsh cleanup/cleanup.ps1` -- what this header used to
# say -- fails with CommandNotFoundException.
#
# Account, region, bucket and the resource-name prefix are read from demo.env so
# this script can never drift away from what the demos actually created. That
# drift was a real bug: this file used to default to us-east-2 and hardcode the
# us-east-2 bucket after the series had been redeployed to us-east-1, so a
# post-class teardown silently deleted nothing and left billable resources up.
#
# Override any of them on the command line for a one-off run.

param(
    [string]$Profile,
    [string]$Region,
    [string]$Bucket,
    [string]$Prefix,
    [switch]$IncludeBucket,
    [switch]$IncludeRole
)

$ErrorActionPreference = "Continue"

# ----------------------------------------------------------------- demo.env
$EnvFile = Join-Path $PSScriptRoot "..\demo.env"
$Conf = @{}
if (Test-Path $EnvFile) {
    foreach ($line in Get-Content $EnvFile) {
        $t = $line.Trim()
        if ($t -and -not $t.StartsWith("#") -and $t.Contains("=")) {
            $k, $v = $t.Split("=", 2)
            $Conf[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
        }
    }
} else {
    Write-Warning "demo.env not found at $EnvFile - falling back to built-in defaults."
}

function Resolve-Setting([string]$Flag, [string]$Key, [string]$Fallback) {
    if ($Flag) { return $Flag }
    if ($Conf.ContainsKey($Key) -and $Conf[$Key]) { return $Conf[$Key] }
    return $Fallback
}

$Account = Resolve-Setting $null      "SMDEMO_ACCOUNT" "000000000000"
$Profile = Resolve-Setting $Profile   "SMDEMO_PROFILE" "default"
$Region  = Resolve-Setting $Region    "SMDEMO_REGION"  "us-east-1"
$Bucket  = Resolve-Setting $Bucket    "SMDEMO_BUCKET"  "roi-smdemo-$Account-$Region"
$Prefix  = Resolve-Setting $Prefix    "SMDEMO_PREFIX"  "roi-smdemo-gas"
$Role    = "roi-smdemo-exec-role"

# Say out loud what we are about to operate on. A teardown pointed at the wrong
# region is indistinguishable from a successful one unless you print this.
Write-Host "== Teardown target ==" -ForegroundColor Cyan
Write-Host "   account : $Account"
Write-Host "   region  : $Region"
Write-Host "   profile : $Profile"
Write-Host "   bucket  : $Bucket"
Write-Host "   prefix  : $Prefix*"
Write-Host ""

Write-Host "== Deleting Glue job, crawler, and demo database =="
aws glue delete-job --job-name "$Prefix-visual-etl" --profile $Profile --region $Region 2>$null
aws glue delete-crawler --name "$Prefix-crawler" --profile $Profile --region $Region 2>$null
aws glue delete-database --name gas_demo --profile $Profile --region $Region 2>$null

Write-Host "== Deleting Feature Store group =="
aws sagemaker delete-feature-group --feature-group-name "$Prefix-features" --profile $Profile --region $Region 2>$null

Write-Host "== Deleting Pipeline, Model Registry, Experiment =="
aws sagemaker delete-pipeline --pipeline-name "$Prefix-pipeline" --profile $Profile --region $Region 2>$null
$pkgs = aws sagemaker list-model-packages --model-package-group-name "$Prefix-models" --profile $Profile --region $Region --query "ModelPackageSummaryList[].ModelPackageArn" --output text 2>$null
foreach ($pkg in ($pkgs -split "\s+" | Where-Object { $_ })) {
    aws sagemaker delete-model-package --model-package-name $pkg --profile $Profile --region $Region 2>$null
}
aws sagemaker delete-model-package-group --model-package-group-name "$Prefix-models" --profile $Profile --region $Region 2>$null
aws sagemaker delete-model --model-name "$Prefix-model" --profile $Profile --region $Region 2>$null
# Experiment runs/trial-components must be deleted before the experiment; the
# SageMaker SDK's experiment cleanup is easiest for this - see note in cleanup.sh.
aws sagemaker delete-experiment --experiment-name "$Prefix-experiment" --profile $Profile --region $Region 2>$null

Write-Host "== Deleting MLflow tracking server + its teardown schedule =="
aws sagemaker delete-mlflow-tracking-server --tracking-server-name "$Prefix-mlflow" --profile $Profile --region $Region 2>$null
aws scheduler delete-schedule --name "$Prefix-mlflow-teardown" --profile $Profile --region $Region 2>$null

Write-Host "== Stopping + deleting EMR Serverless applications =="
# Match BOTH the app this series creates by name AND the ones SageMaker creates
# on our behalf. Opening Data Wrangler / Canvas in a domain auto-provisions an
# EMR Serverless app called "sm-canvas-data-wrangler-emr-app-<user-profile>",
# which no amount of matching on our own prefix will ever find. A July 2026 one
# survived that teardown for exactly this reason and was still there in October.
$apps = aws emr-serverless list-applications --profile $Profile --region $Region `
    --query "applications[?state!='TERMINATED'].[id,name]" --output text
foreach ($line in ($apps -split "`n" | Where-Object { $_.Trim() })) {
    $parts = $line.Trim() -split "\s+"
    $id = $parts[0]
    $name = $parts[1]
    if ($name -notlike "$Prefix*" -and $name -notlike "sm-canvas-*") {
        Write-Host "  skipping unrelated app $name ($id)"
        continue
    }
    aws emr-serverless stop-application --application-id $id --profile $Profile --region $Region 2>$null
    aws emr-serverless delete-application --application-id $id --profile $Profile --region $Region 2>$null
    Write-Host "  deleted app $name ($id)"
}

Write-Host "== Deleting SageMaker endpoints for this demo (modules 3-7) =="
$eps = aws sagemaker list-endpoints --profile $Profile --region $Region `
    --query "Endpoints[?starts_with(EndpointName,'roi-smdemo')].EndpointName" --output text
foreach ($e in ($eps -split "\s+" | Where-Object { $_ })) {
    aws sagemaker delete-endpoint --endpoint-name $e --profile $Profile --region $Region 2>$null
    Write-Host "  deleted endpoint $e"
}

if ($IncludeBucket) {
    Write-Host "== Emptying + deleting bucket $Bucket =="
    aws s3 rm "s3://$Bucket" --recursive --only-show-errors --profile $Profile
    aws s3api delete-bucket --bucket $Bucket --profile $Profile --region $Region 2>$null
} else {
    Write-Host "== Keeping bucket (use -IncludeBucket to delete). Clearing derived data only =="
    aws s3 rm "s3://$Bucket/processed/" --recursive --only-show-errors --profile $Profile
    aws s3 rm "s3://$Bucket/tmp/" --recursive --only-show-errors --profile $Profile
    aws s3 rm "s3://$Bucket/logs/" --recursive --only-show-errors --profile $Profile
}

if ($IncludeRole) {
    Write-Host "== Deleting shared IAM role $Role =="
    aws iam delete-role-policy --role-name $Role --policy-name demo-permissions --profile $Profile 2>$null
    aws iam detach-role-policy --role-name $Role --policy-arn arn:aws:iam::aws:policy/AmazonSageMakerFullAccess --profile $Profile 2>$null
    aws iam delete-role --role-name $Role --profile $Profile 2>$null
}

# ------------------------------------------------------- verification sweep
# Every delete above is silenced with 2>$null so a re-run stays quiet, which
# also means a FAILED delete looks exactly like a successful one. So we now go
# back and look for the things that actually cost money if left running.
Write-Host ""
Write-Host "== Verifying: anything still billable in $Region ? ==" -ForegroundColor Cyan
$leftover = @()
$unchecked = @()

# Run one check. If the installed AWS CLI does not support the operation, say so
# LOUDLY instead of swallowing it: a check that silently cannot run looks
# identical to a check that passed, which is the exact failure this sweep exists
# to prevent. (Real example: aws-cli 2.15 has no
# `sagemaker list-mlflow-tracking-servers`, so that check was dead code -- an
# MLflow tracking server costs real money and would never have been reported.)
function Invoke-Check {
    param([string]$Label, [string[]]$CliArgs)
    $out = & aws @CliArgs 2>&1
    $text = ($out | Out-String)
    if ($LASTEXITCODE -ne 0) {
        if ($text -match "Invalid choice|argument operation") {
            $script:unchecked += "$Label (this aws-cli does not support it - upgrade the CLI)"
        } else {
            $script:unchecked += "$Label (check failed: $($text.Trim() -split "`n" | Select-Object -First 1))"
        }
        return @()
    }
    return ($text -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() })
}

foreach ($e in Invoke-Check "endpoints" @("sagemaker", "list-endpoints", "--profile", $Profile, "--region", $Region, "--query", "Endpoints[].EndpointName", "--output", "text")) {
    $leftover += "endpoint: $e"
}
foreach ($a in Invoke-Check "emr-serverless applications" @("emr-serverless", "list-applications", "--profile", $Profile, "--region", $Region, "--query", "applications[?state!='TERMINATED'].[name,state]", "--output", "text")) {
    $leftover += "emr-serverless: $a"
}
foreach ($m in Invoke-Check "mlflow tracking servers" @("sagemaker", "list-mlflow-tracking-servers", "--profile", $Profile, "--region", $Region, "--query", "TrackingServerSummaries[].TrackingServerName", "--output", "text")) {
    $leftover += "mlflow-server: $m"
}
# Studio / Unified Studio spaces are the classic overnight bill.
foreach ($a in Invoke-Check "studio apps" @("sagemaker", "list-apps", "--profile", $Profile, "--region", $Region, "--query", "Apps[?Status=='InService'].[AppName,AppType]", "--output", "text")) {
    $leftover += "studio app InService: $a"
}

if ($unchecked.Count -gt 0) {
    Write-Host "COULD NOT CHECK - verify these by hand:" -ForegroundColor Yellow
    $unchecked | ForEach-Object { Write-Host "   ? $_" -ForegroundColor Yellow }
    Write-Host ""
}

if ($leftover.Count -gt 0) {
    Write-Host "STILL PRESENT - these can bill until removed:" -ForegroundColor Yellow
    $leftover | ForEach-Object { Write-Host "   ! $_" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "Cleanup finished with leftovers (see above)." -ForegroundColor Yellow
    exit 1
}

if ($unchecked.Count -gt 0) {
    Write-Host "Cleanup complete, but some checks could not run (see above)." -ForegroundColor Yellow
    exit 1
}

Write-Host "   nothing billable found." -ForegroundColor Green
Write-Host ""
Write-Host "Cleanup complete." -ForegroundColor Green
