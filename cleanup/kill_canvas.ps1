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
$deleted = @()
$failed  = @()
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

            # Build the argument list instead of string-splicing into
            # Invoke-Expression, and do NOT swallow stderr.
            #
            # The previous version did `Invoke-Expression "... 2>`$null"`, which
            # meant a FAILED delete printed the same reassuring "deleting ..."
            # line as a successful one. A Canvas app survived five and a half
            # hours of being "killed" that way -- about ten dollars. Same class
            # of bug as everything else in this repo that hid an error: the
            # output said it worked and nobody checked.
            $cliArgs = @(
                "sagemaker", "delete-app",
                "--domain-id", $d,
                "--app-type", $a.AppType,
                "--app-name", $a.AppName
            ) + ($scope -split " ") + @("--profile", $Profile, "--region", $r)

            $out = & aws @cliArgs 2>&1
            if ($LASTEXITCODE -ne 0) {
                $msg = ($out | Out-String).Trim()
                if ($msg -match "does not exist|ResourceNotFound") {
                    Write-Host "    already gone" -ForegroundColor DarkGray
                } else {
                    Write-Host "    DELETE FAILED: $msg" -ForegroundColor Red
                    $script:failed += $label
                }
            } else {
                $script:deleted += $label
            }
        }
    }
}

# ------------------------------------------------------------- verify
# A delete request being accepted is not the same as the app being gone, and
# Canvas takes a minute or two to transition. Poll until nothing of a watched
# type is left, rather than printing "Done" and hoping.
if ($deleted.Count -eq 0 -and $failed.Count -eq 0) {
    Write-Host "Nothing to delete." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "== Verifying the apps are actually gone ==" -ForegroundColor Cyan
for ($i = 1; $i -le 12; $i++) {
    $alive = @()
    foreach ($r in $Region) {
        $domains = aws sagemaker list-domains --profile $Profile --region $r --query "Domains[].DomainId" --output text 2>$null
        foreach ($d in ($domains -split "\s+" | Where-Object { $_ })) {
            $json = aws sagemaker list-apps --domain-id-equals $d --profile $Profile --region $r --output json 2>$null
            if (-not $json) { continue }
            foreach ($a in ($json | ConvertFrom-Json).Apps) {
                if ($killTypes -notcontains $a.AppType) { continue }
                if ($a.Status -in @("Deleted", "Failed")) { continue }
                $alive += "$($a.AppType)/$($a.AppName) [$($a.Status)]"
            }
        }
    }
    if ($alive.Count -eq 0) {
        Write-Host "   confirmed gone." -ForegroundColor Green
        break
    }
    Write-Host "   still present: $($alive -join ', ')"
    if ($i -eq 12) {
        Write-Host ""
        Write-Host "STILL RUNNING after 2 minutes -- these are billing:" -ForegroundColor Red
        $alive | ForEach-Object { Write-Host "   ! $_" -ForegroundColor Red }
        exit 1
    }
    Start-Sleep -Seconds 10
}

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Some deletes errored (see above); re-run to retry." -ForegroundColor Yellow
    exit 1
}
Write-Host "Done." -ForegroundColor Green
