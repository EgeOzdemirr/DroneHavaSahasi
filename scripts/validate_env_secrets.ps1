param(
    [string]$EnvPath = ".env"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvPath)) {
    Write-Error ".env file not found: $EnvPath"
    exit 1
}

function Parse-EnvFile {
    param([string]$Path)
    $map = @{}
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
        if ($trimmed.StartsWith("#")) { continue }
        $idx = $trimmed.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim()
        $map[$key] = $value
    }
    return $map
}

function Is-WeakLiteral {
    param([string]$Value)
    $weak = @(
        "change-me",
        "change-me-for-production",
        "change-me-bridge-token",
        "changeme",
        "default",
        "token",
        "secret",
        "admin123"
    )
    return $weak -contains $Value.ToLowerInvariant()
}

function Test-FernetKey {
    param([string]$Value)
    try {
        $b64 = $Value.Replace('-', '+').Replace('_', '/')
        switch ($b64.Length % 4) {
            2 { $b64 += "==" }
            3 { $b64 += "=" }
            default { }
        }
        $bytes = [Convert]::FromBase64String($b64)
        return $bytes.Length -eq 32
    }
    catch {
        return $false
    }
}

$envMap = Parse-EnvFile -Path $EnvPath
$errors = New-Object System.Collections.Generic.List[string]

if (-not $envMap.ContainsKey("JWT_SECRET_KEY")) {
    $errors.Add("JWT_SECRET_KEY missing.")
}
elseif ($envMap["JWT_SECRET_KEY"].Length -lt 32 -or (Is-WeakLiteral -Value $envMap["JWT_SECRET_KEY"])) {
    $errors.Add("JWT_SECRET_KEY is weak (min 32 chars and non-default required).")
}

if (-not $envMap.ContainsKey("BRIDGE_SOURCE_TOKEN")) {
    $errors.Add("BRIDGE_SOURCE_TOKEN missing.")
}
elseif ($envMap["BRIDGE_SOURCE_TOKEN"].Length -lt 24 -or (Is-WeakLiteral -Value $envMap["BRIDGE_SOURCE_TOKEN"])) {
    $errors.Add("BRIDGE_SOURCE_TOKEN is weak (min 24 chars and non-default required).")
}

if (-not $envMap.ContainsKey("MASTER_KEY")) {
    $errors.Add("MASTER_KEY missing.")
}
elseif (-not (Test-FernetKey -Value $envMap["MASTER_KEY"])) {
    $errors.Add("MASTER_KEY is invalid (must be urlsafe base64 encoded 32-byte Fernet key).")
}

if (-not $envMap.ContainsKey("BOOTSTRAP_ADMIN_PASSWORD")) {
    $errors.Add("BOOTSTRAP_ADMIN_PASSWORD missing.")
}
elseif ($envMap["BOOTSTRAP_ADMIN_PASSWORD"].Length -lt 12 -or (Is-WeakLiteral -Value $envMap["BOOTSTRAP_ADMIN_PASSWORD"])) {
    $errors.Add("BOOTSTRAP_ADMIN_PASSWORD is weak (min 12 chars and non-default required).")
}

if ($errors.Count -gt 0) {
    Write-Host "Secret validation failed:" -ForegroundColor Red
    foreach ($err in $errors) {
        Write-Host "- $err" -ForegroundColor Red
    }
    exit 1
}

Write-Host "Secret validation passed." -ForegroundColor Green
