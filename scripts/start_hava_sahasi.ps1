param(
    [string]$Url = "http://localhost:8000/ui/login",
    [int]$TimeoutSeconds = 180,
    [switch]$NoBrowser,
    [switch]$SkipBuild,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Write-Step {
    param([string]$Message)
    Write-Host "[..] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Assert-RequiredFiles {
    $envPath = Join-Path $repoRoot ".env"
    $composePath = Join-Path $repoRoot "docker-compose.yml"

    if (-not (Test-Path $composePath)) {
        throw "docker-compose.yml not found: $composePath"
    }
    if (-not (Test-Path $envPath)) {
        throw ".env not found. Create it first: Copy-Item .env.example .env"
    }
}

function Assert-DockerCli {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI not found. Install Docker Desktop and make sure docker is on PATH."
    }
}

function Test-DockerReady {
    try {
        docker info --format "{{.ServerVersion}}" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Start-DockerDesktopIfAvailable {
    $candidates = @()
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe")
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe")
    }
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            Write-Step "Starting Docker Desktop"
            Start-Process -FilePath $candidate -WindowStyle Hidden | Out-Null
            return
        }
    }

    throw "Docker engine is not running and Docker Desktop executable was not found."
}

function Wait-DockerReady {
    param([int]$Timeout)

    if (Test-DockerReady) {
        Write-Ok "Docker engine is ready"
        return
    }

    Start-DockerDesktopIfAvailable
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerReady) {
            Write-Ok "Docker engine is ready"
            return
        }
        Start-Sleep -Seconds 3
    }

    throw "Docker engine did not become ready within $Timeout seconds."
}

function Invoke-ComposeUp {
    $args = @("compose", "up", "-d")
    if (-not $SkipBuild) {
        $args += "--build"
    }

    Write-Step "Running: docker $($args -join ' ')"
    & docker @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($args -join ' ') failed with exit code $LASTEXITCODE"
    }
    Write-Ok "Docker services started"
}

function Test-UrlReady {
    param([string]$TargetUrl)

    try {
        $response = Invoke-WebRequest -Uri $TargetUrl -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

function Wait-UrlReady {
    param(
        [string]$TargetUrl,
        [int]$Timeout
    )

    Write-Step "Waiting for $TargetUrl"
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        if (Test-UrlReady -TargetUrl $TargetUrl) {
            Write-Ok "Login page is ready"
            return
        }
        Start-Sleep -Seconds 3
    }

    throw "Login page did not become ready within $Timeout seconds: $TargetUrl"
}

function Get-PreferredBrowser {
    $chromeCandidates = @()
    if ($env:ProgramFiles) {
        $chromeCandidates += (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe")
    }
    if (${env:ProgramFiles(x86)}) {
        $chromeCandidates += (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe")
    }
    if ($env:LOCALAPPDATA) {
        $chromeCandidates += (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    }

    foreach ($candidate in $chromeCandidates) {
        if (Test-Path $candidate) {
            return @{ Name = "Google Chrome"; Path = $candidate }
        }
    }

    return @{ Name = "default browser"; Path = $null }
}

function Open-LoginBrowser {
    param([string]$TargetUrl)

    $browser = Get-PreferredBrowser
    Write-Step "Opening $($browser.Name): $TargetUrl"
    if ($browser.Path) {
        Start-Process -FilePath $browser.Path -ArgumentList $TargetUrl
    } else {
        Start-Process $TargetUrl
    }
}

function Write-Diagnostics {
    Write-Host ""
    Write-Warn "Diagnostics"
    Write-Host "Expected URL: $Url"
    Write-Host "Repository: $repoRoot"

    try {
        Write-Host ""
        Write-Host "docker info:"
        docker info --format "ServerVersion={{.ServerVersion}}"
    }
    catch {
        Write-Host "docker info failed: $($_.Exception.Message)"
    }

    try {
        Write-Host ""
        Write-Host "docker compose ps:"
        docker compose ps
    }
    catch {
        Write-Host "docker compose ps failed: $($_.Exception.Message)"
    }
}

try {
    if ($TimeoutSeconds -lt 1) {
        throw "TimeoutSeconds must be greater than 0."
    }

    Set-Location $repoRoot
    Write-Step "Repository: $repoRoot"
    Assert-RequiredFiles
    Assert-DockerCli

    $composeCommand = if ($SkipBuild) { "docker compose up -d" } else { "docker compose up -d --build" }
    if ($DryRun) {
        Write-Host "[DRY-RUN] Would wait for Docker engine, starting Docker Desktop if needed."
        Write-Host "[DRY-RUN] Would run: $composeCommand"
        Write-Host "[DRY-RUN] Would wait for: $Url"
        if ($NoBrowser) {
            Write-Host "[DRY-RUN] Browser launch disabled by -NoBrowser."
        } else {
            $browser = Get-PreferredBrowser
            Write-Host "[DRY-RUN] Would open $($browser.Name) at: $Url"
        }
        exit 0
    }

    Wait-DockerReady -Timeout $TimeoutSeconds
    Invoke-ComposeUp
    Wait-UrlReady -TargetUrl $Url -Timeout $TimeoutSeconds

    if ($NoBrowser) {
        Write-Ok "Ready. Browser launch skipped. Open: $Url"
    } else {
        Open-LoginBrowser -TargetUrl $Url
        Write-Ok "Ready"
    }
}
catch {
    Write-Host "[FAIL] $($_.Exception.Message)" -ForegroundColor Red
    Write-Diagnostics
    exit 1
}
