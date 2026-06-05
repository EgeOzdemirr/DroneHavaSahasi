param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Username = "admin",
    [string]$Password = "admin123",
    [switch]$UseBridge,
    [string]$BridgeUrl = "http://localhost:8100",
    [string]$BridgeToken = "change-me-bridge-token",
    [switch]$ResetDatabase = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function To-JsonString([object]$Value) {
    return ($Value | ConvertTo-Json -Depth 8 -Compress)
}

function Get-HexSha256([string]$Text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        $hash = $sha.ComputeHash($bytes)
        return ([BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-HexHmacSha256([string]$Secret, [string]$Text) {
    $hmac = [System.Security.Cryptography.HMACSHA256]::new([System.Text.Encoding]::UTF8.GetBytes($Secret))
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        $hash = $hmac.ComputeHash($bytes)
        return ([BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $hmac.Dispose()
    }
}

function New-TelemetryPacket {
    param(
        [Parameter(Mandatory = $true)][string]$DroneUid,
        [Parameter(Mandatory = $true)][string]$Secret,
        [Parameter(Mandatory = $true)][hashtable]$Payload,
        [string]$OverrideSignature
    )

    $ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    $nonce = [Guid]::NewGuid().ToString()
    $body = To-JsonString $Payload
    $bodyHash = Get-HexSha256 $body
    $canonical = "$DroneUid`n$ts`n$nonce`n$bodyHash"
    $signature = if ($OverrideSignature) { $OverrideSignature } else { Get-HexHmacSha256 -Secret $Secret -Text $canonical }

    $headers = @{
        "X-Drone-Uid" = $DroneUid
        "X-Ts" = $ts
        "X-Nonce" = $nonce
        "X-Signature" = $signature
        "X-Sig-Version" = "hmac-sha256-v1"
    }
    if ($UseBridge) {
        $headers["X-Bridge-Token"] = $BridgeToken
    }

    return [PSCustomObject]@{
        Headers = $headers
        Body = $body
    }
}

function Send-TelemetryPacket {
    param(
        [Parameter(Mandatory = $true)][pscustomobject]$Packet
    )

    $targetUri = if ($UseBridge) { "$BridgeUrl/bridge/v1/telemetry/ingest" } else { "$BaseUrl/v1/telemetry/ingest" }
    return Invoke-RestMethod -Method Post -Uri $targetUri -Headers $Packet.Headers -ContentType "application/json" -Body $Packet.Body
}

function New-Drone {
    param(
        [Parameter(Mandatory = $true)][string]$DroneUid,
        [Parameter(Mandatory = $true)][hashtable]$AuthHeaders
    )
    $body = To-JsonString @{
        drone_uid = $DroneUid
        unit = "Alpha"
        status = "active"
    }
    return Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/drones" -Headers $AuthHeaders -ContentType "application/json" -Body $body
}

Write-Step "Login"
$loginBody = To-JsonString @{ username = $Username; password = $Password }
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/auth/login" -ContentType "application/json" -Body $loginBody
$authHeaders = @{ Authorization = "Bearer $($login.access_token)" }

if ($ResetDatabase) {
    Write-Step "Reset tactical tables (users preserved)"
    $sql = @"
TRUNCATE TABLE telemetry_events, track_state, alerts, mission_assignments, missions, drones, drone_keys, audit_log RESTART IDENTITY CASCADE;
"@
    docker compose exec -T postgres psql -U postgres -d friend_drone -c $sql | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Database reset failed. Re-run with elevated Docker privileges or pass -ResetDatabase:`$false."
    }
}

$runId = Get-Date -Format "yyyyMMddHHmmss"
$uidAuthorized = "AUTH-$runId"
$uidRegisteredNotAuth = "REGNA-$runId"
$uidSuspicious = "SUS-$runId"
$uidUnknown = "UNK-$runId"

Write-Step "Create 3 registered drones"
$droneAuthorized = New-Drone -DroneUid $uidAuthorized -AuthHeaders $authHeaders
$droneRegisteredNotAuth = New-Drone -DroneUid $uidRegisteredNotAuth -AuthHeaders $authHeaders
$droneSuspicious = New-Drone -DroneUid $uidSuspicious -AuthHeaders $authHeaders

Write-Step "Create active mission for AUTHORIZED drone"
$now = (Get-Date).ToUniversalTime()
$missionBody = To-JsonString @{
    name = "Minimal Tactical Mission $runId"
    starts_at = $now.AddMinutes(-3).ToString("o")
    ends_at = $now.AddHours(1).ToString("o")
}
$mission = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions" -Headers $authHeaders -ContentType "application/json" -Body $missionBody
$assignmentBody = To-JsonString @{
    drone_id = $droneAuthorized.drone.id
    role = "recon"
}
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions/$($mission.id)/assignments" -Headers $authHeaders -ContentType "application/json" -Body $assignmentBody | Out-Null
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions/$($mission.id)/approve" -Headers $authHeaders | Out-Null

Write-Step "Seed AUTHORIZED with moving playback points"
for ($i = 0; $i -lt 10; $i++) {
    $lat = 41.0000 + ($i * 0.0012)
    $lon = 29.0000 + ($i * 0.0008)
    $payload = @{
        lat = [math]::Round($lat, 6)
        lon = [math]::Round($lon, 6)
        alt_m = 110 + $i
        speed_mps = 14.0 + ($i * 0.3)
        heading_deg = 75.0
        seq = $i + 1
        source = "seed-minimal"
    }
    $packet = New-TelemetryPacket -DroneUid $uidAuthorized -Secret $droneAuthorized.shared_secret -Payload $payload
    $null = Send-TelemetryPacket -Packet $packet
    Start-Sleep -Milliseconds 120
}

Write-Step "Seed REGISTERED_NOT_AUTHORIZED"
$payloadReg = @{
    lat = 40.975
    lon = 28.945
    alt_m = 90
    speed_mps = 8.5
    heading_deg = 45
    seq = 1
    source = "seed-minimal"
}
$packetReg = New-TelemetryPacket -DroneUid $uidRegisteredNotAuth -Secret $droneRegisteredNotAuth.shared_secret -Payload $payloadReg
$respReg = Send-TelemetryPacket -Packet $packetReg

Write-Step "Seed SUSPICIOUS (bad_signature)"
$payloadSus = @{
    lat = 41.045
    lon = 29.03
    alt_m = 130
    speed_mps = 16.2
    heading_deg = 92
    seq = 1
    source = "seed-minimal"
}
$packetSus = New-TelemetryPacket -DroneUid $uidSuspicious -Secret $droneSuspicious.shared_secret -Payload $payloadSus
$packetSus.Headers["X-Signature"] = "00" + $packetSus.Headers["X-Signature"].Substring(2)
$respSus = Send-TelemetryPacket -Packet $packetSus

Write-Step "Seed UNKNOWN"
$payloadUnknown = @{
    lat = 41.06
    lon = 28.88
    alt_m = 125
    speed_mps = 12.0
    heading_deg = 125
    seq = 1
    source = "seed-minimal"
}
$packetUnknown = New-TelemetryPacket -DroneUid $uidUnknown -Secret "unknown-secret-$runId" -Payload $payloadUnknown
$respUnknown = Send-TelemetryPacket -Packet $packetUnknown

Write-Step "Fetch tactical summary"
$summary = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/tracks/summary" -Headers $authHeaders
$tracks = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/tracks" -Headers $authHeaders

Write-Host ("Summary: AUTHORIZED={0} REGISTERED_NOT_AUTHORIZED={1} UNKNOWN={2} SUSPICIOUS={3}" -f `
    $summary.authorized, $summary.registered_not_authorized, $summary.unknown, $summary.suspicious) -ForegroundColor Green
Write-Host ("Tracks in table: {0}" -f (($tracks | Measure-Object).Count)) -ForegroundColor Green
Write-Host ("AUTHORIZED UID: {0}" -f $uidAuthorized)
Write-Host ("REGISTERED_NOT_AUTHORIZED UID: {0} -> {1}/{2}" -f $uidRegisteredNotAuth, $respReg.status, $respReg.reason)
Write-Host ("SUSPICIOUS UID: {0} -> {1}/{2}" -f $uidSuspicious, $respSus.status, $respSus.reason)
Write-Host ("UNKNOWN UID: {0} -> {1}/{2}" -f $uidUnknown, $respUnknown.status, $respUnknown.reason)
Write-Host "UI: http://localhost:8000/ui/tactical (authorized drone'u secip Playback Yukle yapin)." -ForegroundColor Yellow
