param(
    [string]$EnvPath = ".env",
    [string]$ApiBaseUrl = "http://localhost:8000",
    [string]$BridgeBaseUrl = "http://localhost:8100",
    [switch]$SkipNtpCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:HasFailure = $false

function Invoke-Check {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    try {
        & $Action
        Write-Host "[ OK ] $Name" -ForegroundColor Green
    }
    catch {
        $script:HasFailure = $true
        Write-Host "[FAIL] $Name -> $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Parse-EnvFile {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path $Path)) {
        return $map
    }
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

function Get-FirstRevision {
    param([string]$Text)
    $match = [regex]::Match($Text, "([0-9]{8}_[0-9]{4})")
    if (-not $match.Success) {
        throw "Revision id parse edilemedi: $Text"
    }
    return $match.Groups[1].Value
}

$envMap = Parse-EnvFile -Path $EnvPath
$postgresUser = if ($envMap.ContainsKey("POSTGRES_USER")) { $envMap["POSTGRES_USER"] } else { "postgres" }
$postgresDb = if ($envMap.ContainsKey("POSTGRES_DB")) { $envMap["POSTGRES_DB"] } else { "friend_drone" }

Invoke-Check -Name "Secret validation (.env)" -Action {
    $validator = Join-Path $PSScriptRoot "validate_env_secrets.ps1"
    if (-not (Test-Path $validator)) {
        throw "validate_env_secrets.ps1 bulunamadi: $validator"
    }
    powershell -ExecutionPolicy Bypass -File $validator -EnvPath $EnvPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Secret validation basarisiz (exit=$LASTEXITCODE)"
    }
}

Invoke-Check -Name "API reachability" -Action {
    $resp = Invoke-WebRequest -Uri "$($ApiBaseUrl.TrimEnd('/'))/openapi.json" -UseBasicParsing -TimeoutSec 8
    if ($resp.StatusCode -ne 200) {
        throw "API openapi status beklenen=200 gercek=$($resp.StatusCode)"
    }
}

Invoke-Check -Name "Bridge health endpoint" -Action {
    $health = Invoke-RestMethod -Method GET -Uri "$($BridgeBaseUrl.TrimEnd('/'))/bridge/v1/health" -TimeoutSec 8
    if (-not $health) {
        throw "Bridge health response bos"
    }
    if ($health.status -ne "ok") {
        throw "Bridge health status beklenen=ok gercek=$($health.status)"
    }
}

Invoke-Check -Name "Docker compose services running" -Action {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "docker komutu bulunamadi"
    }
    $psRaw = docker compose ps --format json
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose ps calismadi"
    }
    $lines = ($psRaw -split "`r?`n") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    if ($lines.Count -eq 0) {
        throw "docker compose ps bos dondu"
    }
    $rows = @()
    foreach ($line in $lines) {
        $rows += ($line | ConvertFrom-Json)
    }
    $required = @(
        "friend-drone-api",
        "friend-drone-bridge",
        "friend-drone-postgres",
        "friend-drone-redis"
    )
    foreach ($name in $required) {
        $row = $rows | Where-Object { $_.Name -eq $name } | Select-Object -First 1
        if (-not $row) {
            throw "Container listesinde yok: $name"
        }
        if ($row.State -ne "running") {
            throw "Container running degil: $name (state=$($row.State))"
        }
    }
}

Invoke-Check -Name "Postgres health (pg_isready)" -Action {
    docker compose exec -T postgres pg_isready -U $postgresUser -d $postgresDb | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pg_isready basarisiz (user=$postgresUser db=$postgresDb)"
    }
}

Invoke-Check -Name "Redis health (PING)" -Action {
    $pong = docker compose exec -T redis redis-cli ping
    if ($LASTEXITCODE -ne 0) {
        throw "redis-cli ping basarisiz"
    }
    if (-not ($pong -match "PONG")) {
        throw "redis ping yaniti beklenen=PONG gercek=$pong"
    }
}

Invoke-Check -Name "Alembic migration up-to-date" -Action {
    $currentRaw = docker compose exec -T api alembic current
    if ($LASTEXITCODE -ne 0) {
        throw "alembic current basarisiz"
    }
    $headsRaw = docker compose exec -T api alembic heads
    if ($LASTEXITCODE -ne 0) {
        throw "alembic heads basarisiz"
    }
    $current = Get-FirstRevision -Text ($currentRaw | Out-String)
    $head = Get-FirstRevision -Text ($headsRaw | Out-String)
    if ($current -ne $head) {
        throw "migration drift var (current=$current head=$head)"
    }
}

if (-not $SkipNtpCheck) {
    if (Get-Command w32tm -ErrorAction SilentlyContinue) {
        try {
            $statusRaw = (w32tm /query /status 2>$null) | Out-String
            $srcMatch = [regex]::Match($statusRaw, "Source:\s*(.+)")
            if ($srcMatch.Success) {
                $source = $srcMatch.Groups[1].Value.Trim()
                if ($source -eq "Local CMOS Clock") {
                    Write-Host "[WARN] NTP source Local CMOS Clock, clock skew riski artar." -ForegroundColor Yellow
                } else {
                    Write-Host "[ OK ] NTP source: $source" -ForegroundColor Green
                }
            } else {
                Write-Host "[WARN] NTP source parse edilemedi, manuel kontrol onerilir." -ForegroundColor Yellow
            }
        }
        catch {
            Write-Host "[WARN] NTP kontrolu calismadi: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[WARN] w32tm bulunamadi, NTP kontrolu atlandi." -ForegroundColor Yellow
    }
}

if ($script:HasFailure) {
    Write-Host "Preflight check FAILED." -ForegroundColor Red
    exit 1
}

Write-Host "Preflight check PASSED." -ForegroundColor Green
exit 0

