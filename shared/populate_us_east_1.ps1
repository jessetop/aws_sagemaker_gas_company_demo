# One-shot "populate" for the us-east-1 domains after `terraform apply`.
# 1) sync the dataset into the in-region bucket
# 2) register the raw data in the Glue Data Catalog (surfaces in Unified Studio's
#    data explorer / Lakehouse)
# 3) create + ingest the SageMaker Feature Store group (populates SageMaker AI)
#
#   pwsh shared/populate_us_east_1.ps1
#   pwsh shared/populate_us_east_1.ps1 -SkipSync        # data already copied
#   pwsh shared/populate_us_east_1.ps1 -SkipFeatureStore
#
param(
    [string]$Profile = "roitraining",
    [string]$Region  = "us-east-1",
    [string]$Bucket  = "roi-smdemo-029331796573-us-east-1",
    [string]$RoleArn = "arn:aws:iam::029331796573:role/roi-smdemo-exec-role",
    [string]$GlueDatabase = "taxi_demo",
    [switch]$SkipSync,
    [switch]$SkipCatalog,
    [switch]$SkipFeatureStore
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

if (-not $SkipSync) {
    Write-Host "== [1/3] Sync dataset us-east-2 -> $Bucket ==" -ForegroundColor Cyan
    & "$PSScriptRoot/sync_data_to_us_east_1.ps1" -Profile $Profile -Dest $Bucket
}

if (-not $SkipCatalog) {
    Write-Host "== [2/3] Register raw data in Glue Data Catalog ($GlueDatabase) ==" -ForegroundColor Cyan
    aws glue create-database --database-input "{`"Name`":`"$GlueDatabase`"}" --profile $Profile --region $Region 2>$null
    $crawler = "roi-smdemo-taxi-crawler"
    $targets = "{`"S3Targets`":[{`"Path`":`"s3://$Bucket/raw/trips/`"},{`"Path`":`"s3://$Bucket/raw/zones/`"}]}"
    aws glue create-crawler --name $crawler --role $RoleArn --database-name $GlueDatabase `
        --targets $targets --profile $Profile --region $Region 2>$null
    aws glue start-crawler --name $crawler --profile $Profile --region $Region
    Write-Host "  crawler started; tables will appear in Unified Studio once it finishes (~1-2 min)."
}

if (-not $SkipFeatureStore) {
    Write-Host "== [3/3] Create + ingest SageMaker Feature Store group ==" -ForegroundColor Cyan
    python "$root/03-feature-store/feature_store_ingest.py" `
        --bucket $Bucket --role-arn $RoleArn --profile $Profile --region $Region --rows 2000
}

Write-Host "Populate complete. Open Unified Studio: https://dzd-b6xs075popdjhj.sagemaker.us-east-1.on.aws" -ForegroundColor Green
