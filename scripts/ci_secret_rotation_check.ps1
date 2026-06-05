Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Get-GeneratedValue {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Key
    )
    $pattern = "(?m)^$Key=(.+)$"
    $match = [regex]::Match($Text, $pattern)
    if (-not $match.Success) {
        throw "$Key not generated."
    }
    return $match.Groups[1].Value.Trim()
}

Write-Host "[STEP] Generate strong secrets"
$generatedText = (& powershell -ExecutionPolicy Bypass -File ".\scripts\generate_secrets.ps1" | Out-String)
$jwtSecret = Get-GeneratedValue -Text $generatedText -Key "JWT_SECRET_KEY"
$bridgeToken = Get-GeneratedValue -Text $generatedText -Key "BRIDGE_SOURCE_TOKEN"
$masterKey = Get-GeneratedValue -Text $generatedText -Key "MASTER_KEY"
$bootstrapPassword = Get-GeneratedValue -Text $generatedText -Key "BOOTSTRAP_ADMIN_PASSWORD"

$goodEnvPath = Join-Path $env:TEMP "friend_drone_good.env"
$badEnvPath = Join-Path $env:TEMP "friend_drone_bad.env"

try {
    Write-Host "[STEP] Validate generated strong env"
    @(
        "JWT_SECRET_KEY=$jwtSecret",
        "BRIDGE_SOURCE_TOKEN=$bridgeToken",
        "MASTER_KEY=$masterKey",
        "BOOTSTRAP_ADMIN_PASSWORD=$bootstrapPassword"
    ) | Set-Content -Path $goodEnvPath

    & powershell -ExecutionPolicy Bypass -File ".\scripts\validate_env_secrets.ps1" -EnvPath $goodEnvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Strong env validation failed unexpectedly."
    }

    Write-Host "[STEP] Validate weak env is rejected"
    @(
        "JWT_SECRET_KEY=change-me",
        "BRIDGE_SOURCE_TOKEN=change-me-bridge-token",
        "MASTER_KEY=invalid-key",
        "BOOTSTRAP_ADMIN_PASSWORD=admin123"
    ) | Set-Content -Path $badEnvPath

    & powershell -ExecutionPolicy Bypass -File ".\scripts\validate_env_secrets.ps1" -EnvPath $badEnvPath
    if ($LASTEXITCODE -eq 0) {
        throw "Weak env validation unexpectedly passed."
    }
    Write-Host "[ OK ] Weak env rejected as expected."
}
finally {
    if (Test-Path $goodEnvPath) { Remove-Item $goodEnvPath -Force }
    if (Test-Path $badEnvPath) { Remove-Item $badEnvPath -Force }
}

Write-Host "[DONE] CI secret rotation checks passed."

$LASTEXITCODE = 0
exit 0