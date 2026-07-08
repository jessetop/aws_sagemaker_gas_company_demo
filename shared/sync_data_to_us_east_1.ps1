# Copy the project dataset from the old us-east-2 bucket into the new in-region
# us-east-1 bucket, so Feature Store / Clarify / training run alongside the
# us-east-1 domains. Same account, so this is a server-side S3 copy (fast, cheap).
#
# Run AFTER `terraform apply` has created the destination bucket.
#
#   pwsh shared/sync_data_to_us_east_1.ps1
#   pwsh shared/sync_data_to_us_east_1.ps1 -RawOnly     # just raw/ (skip derived data)
#   pwsh shared/sync_data_to_us_east_1.ps1 -DryRun
#
param(
    [string]$Profile = "roitraining",
    [string]$Source  = "roi-smdemo-029331796573-us-east-2",
    [string]$Dest    = "roi-smdemo-029331796573-us-east-1",
    [switch]$RawOnly,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Sanity: destination must exist (Terraform creates it).
$null = aws s3api head-bucket --bucket $Dest --profile $Profile 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Destination bucket s3://$Dest not found. Run 'terraform apply' first."
    exit 1
}

$prefixes = if ($RawOnly) { @("raw/") } else { @("") }  # "" = whole bucket

foreach ($p in $prefixes) {
    $src = "s3://$Source/$p"
    $dst = "s3://$Dest/$p"
    Write-Host "== sync $src -> $dst ==" -ForegroundColor Cyan
    $args = @("s3", "sync", $src, $dst, "--profile", $Profile, "--source-region", "us-east-2", "--region", "us-east-1")
    if ($DryRun) { $args += "--dryrun" }
    aws @args
}

Write-Host "Done. Verify: aws s3 ls s3://$Dest/ --profile $Profile" -ForegroundColor Green
