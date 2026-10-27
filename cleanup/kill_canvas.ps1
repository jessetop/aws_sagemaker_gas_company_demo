# Immediately kill running SageMaker Canvas apps (the ~$50/day biller).
# Scans the given regions, lists apps, and deletes Canvas sessions on demand.
# The Terraform-managed reaper handles this automatically on a schedule; this is
# the manual "kill it now" button.
#
#   pwsh cleanup/kill_canvas.ps1                 # kill Canvas apps in us-east-1 + us-east-2
#   pwsh cleanup/kill_canvas.ps1 -All            # also kill JupyterLab/KernelGateway apps
#   pwsh cleanup/kill_canvas.ps1 -Region us-east-1
#   pwsh cleanup/kill_canvas.ps1 -WhatIf         # list only, delete nothing
#
param(
    [string]$Profile = "default",
    [string[]]$Region = @("us-east-1", "us-east-2"),
    [switch]$All,
    [switch]$WhatIf
)

$ErrorActionPreference = "Continue"
$killTypes = if ($All) { @("Canvas", "JupyterLab", "KernelGateway", "RStudioServerPro", "RSession", "TensorBoard", "DetailedProfiler", "CodeEditor") } else { @("Canvas") }

foreach ($r in $Region) {
    Write-Host "== Region $r : scanning apps ==" -ForegroundColor Cyan
    $domains = aws sagemaker list-domains --profile $Profile --region $r --query "Domains[].DomainId" --output text 2>$null
    foreach ($d in ($domains -split "\s+" | Where-Object { $_ })) {
        $appsJson = aws sagemaker list-apps --domain-id-equals $d --profile $Profile --region $r --output json 2>$null
        if (-not $appsJson) { continue }
        $apps = ($appsJson | ConvertFrom-Json).Apps
        foreach ($a in $apps) {
            if ($killTypes -notcontains $a.AppType) { continue }
            if ($a.Status -in @("Deleting", "Deleted", "Failed")) { continue }
            $scope = if ($a.UserProfileName) { "--user-profile-name $($a.UserProfileName)" } else { "--space-name $($a.SpaceName)" }
            $label = "$($a.AppType)/$($a.AppName) [$($a.Status)] in $d"
            if ($WhatIf) {
                Write-Host "  WOULD DELETE $label" -ForegroundColor Yellow
                continue
            }
            Write-Host "  deleting $label" -ForegroundColor Red
            Invoke-Expression "aws sagemaker delete-app --domain-id $d --app-type $($a.AppType) --app-name $($a.AppName) $scope --profile $Profile --region $r 2>`$null"
        }
    }
}

Write-Host "Done. Canvas apps take a minute or two to fully transition to Deleted." -ForegroundColor Green
