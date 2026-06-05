param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Username = "admin",
    [string]$Password = "admin123",
    [switch]$UseBridge,
    [string]$BridgeUrl = "http://localhost:8100",
    [string]$BridgeToken = "change-me-bridge-token"
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
        [string]$Ts,
        [string]$Nonce,
        [string]$OverrideSignature
    )

    if ([string]::IsNullOrWhiteSpace($Ts)) {
        $Ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    }
    if ([string]::IsNullOrWhiteSpace($Nonce)) {
        $Nonce = [Guid]::NewGuid().ToString()
    }

    $body = To-JsonString $Payload
    $bodyHash = Get-HexSha256 $body
    $canonical = "$DroneUid`n$Ts`n$Nonce`n$bodyHash"
    $signature = if ($OverrideSignature) { $OverrideSignature } else { Get-HexHmacSha256 -Secret $Secret -Text $canonical }

    $headers = @{
        "X-Drone-Uid" = $DroneUid
        "X-Ts" = $Ts
        "X-Nonce" = $Nonce
        "X-Signature" = $signature
        "X-Sig-Version" = "hmac-sha256-v1"
    }

    return [PSCustomObject]@{
        DroneUid = $DroneUid
        Ts = $Ts
        Nonce = $Nonce
        Signature = $signature
        Body = $body
        Headers = $headers
    }
}

function Send-Packet {
    param(
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [Parameter(Mandatory = $true)][pscustomobject]$Packet
    )

    $targetUri = if ($UseBridge) { "$BridgeUrl/bridge/v1/telemetry/ingest" } else { "$BaseUrl/v1/telemetry/ingest" }
    $headers = @{}
    foreach ($key in $Packet.Headers.Keys) {
        $headers[$key] = $Packet.Headers[$key]
    }
    if ($UseBridge) {
        $headers["X-Bridge-Token"] = $BridgeToken
    }

    return Invoke-RestMethod -Method Post `
        -Uri $targetUri `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $Packet.Body
}

function Show-Result {
    param(
        [Parameter(Mandatory = $true)][string]$Scenario,
        [Parameter(Mandatory = $true)]$Response,
        [Parameter(Mandatory = $true)][string]$ExpectedStatus,
        [Parameter(Mandatory = $true)][string]$ExpectedReason
    )

    $isOk = ($Response.status -eq $ExpectedStatus -and $Response.reason -eq $ExpectedReason)
    $color = if ($isOk) { "Green" } else { "Yellow" }
    $mark = if ($isOk) { "PASS" } else { "CHECK" }

    Write-Host ("[{0}] {1}" -f $mark, $Scenario) -ForegroundColor $color
    Write-Host ("  status={0} reason={1} confidence={2} signature_valid={3}" -f $Response.status, $Response.reason, $Response.confidence, $Response.signature_valid)
    if (-not $isOk) {
        Write-Host ("  expected status={0} reason={1}" -f $ExpectedStatus, $ExpectedReason) -ForegroundColor Yellow
    }
}

Write-Step "Login"
$loginBody = To-JsonString @{ username = $Username; password = $Password }
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/auth/login" -ContentType "application/json" -Body $loginBody
$token = $login.access_token
$authHeaders = @{ Authorization = "Bearer $token" }

$runId = Get-Date -Format "yyyyMMddHHmmss"
$droneUid = "DRN-$runId"
$unknownUid = "UNK-$runId"

Write-Step "Create drone registry record"
$createDroneBody = To-JsonString @{
    drone_uid = $droneUid
    unit = "Alpha"
    status = "active"
}
$drone = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/drones" -Headers $authHeaders -ContentType "application/json" -Body $createDroneBody
$droneId = $drone.drone.id
$sharedSecret = $drone.shared_secret

Write-Step "Create and approve mission"
$now = (Get-Date).ToUniversalTime()
$missionBody = To-JsonString @{
    name = "Demo Mission $runId"
    starts_at = $now.AddMinutes(-5).ToString("o")
    ends_at = $now.AddHours(1).ToString("o")
}
$mission = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions" -Headers $authHeaders -ContentType "application/json" -Body $missionBody
$assignmentBody = To-JsonString @{
    drone_id = $droneId
    role = "recon"
}
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions/$($mission.id)/assignments" -Headers $authHeaders -ContentType "application/json" -Body $assignmentBody | Out-Null
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions/$($mission.id)/approve" -Headers $authHeaders | Out-Null

$basePayload = @{
    lat = 41.015
    lon = 28.979
    alt_m = 120.5
    speed_mps = 17.2
    heading_deg = 95.0
    source = "demo-script"
}

Write-Step "Scenario 1: AUTHORIZED"
$payloadAuthorized = $basePayload.Clone()
$payloadAuthorized.seq = 1
$packetAuthorized = New-TelemetryPacket -DroneUid $droneUid -Secret $sharedSecret -Payload $payloadAuthorized
$respAuthorized = Send-Packet -BaseUrl $BaseUrl -Packet $packetAuthorized
Show-Result -Scenario "AUTHORIZED baseline" -Response $respAuthorized -ExpectedStatus "AUTHORIZED" -ExpectedReason "ok"

Write-Step "Scenario 2: UNKNOWN (not in registry)"
$payloadUnknown = $basePayload.Clone()
$payloadUnknown.seq = 2
$packetUnknown = New-TelemetryPacket -DroneUid $unknownUid -Secret "unknown-secret-$runId" -Payload $payloadUnknown
$respUnknown = Send-Packet -BaseUrl $BaseUrl -Packet $packetUnknown
Show-Result -Scenario "UNKNOWN drone" -Response $respUnknown -ExpectedStatus "UNKNOWN" -ExpectedReason "not_in_registry"

Write-Step "Scenario 3: SUSPICIOUS (bad signature)"
$payloadBad = $basePayload.Clone()
$payloadBad.seq = 3
$packetBad = New-TelemetryPacket -DroneUid $droneUid -Secret $sharedSecret -Payload $payloadBad
$badSig = if ($packetBad.Signature.StartsWith("a")) { "b" + $packetBad.Signature.Substring(1) } else { "a" + $packetBad.Signature.Substring(1) }
$packetBad.Headers["X-Signature"] = $badSig
$respBad = Send-Packet -BaseUrl $BaseUrl -Packet $packetBad
Show-Result -Scenario "Tampered signature" -Response $respBad -ExpectedStatus "SUSPICIOUS" -ExpectedReason "bad_signature"

Write-Step "Scenario 4: SUSPICIOUS (replay)"
$payloadReplay = $basePayload.Clone()
$payloadReplay.seq = 4
$packetReplay = New-TelemetryPacket -DroneUid $droneUid -Secret $sharedSecret -Payload $payloadReplay
$respReplayFirst = Send-Packet -BaseUrl $BaseUrl -Packet $packetReplay
Show-Result -Scenario "Replay first send" -Response $respReplayFirst -ExpectedStatus "AUTHORIZED" -ExpectedReason "ok"
$respReplaySecond = Send-Packet -BaseUrl $BaseUrl -Packet $packetReplay
Show-Result -Scenario "Replay second send" -Response $respReplaySecond -ExpectedStatus "SUSPICIOUS" -ExpectedReason "replay_detected"

Write-Step "Fetch tactical summary"
$summary = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/tracks/summary" -Headers $authHeaders
$alerts = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/alerts?status_filter=open" -Headers $authHeaders
$alertCount = if ($null -eq $alerts) { 0 } elseif ($alerts -is [System.Array]) { $alerts.Count } else { 1 }
Write-Host ("Summary: AUTHORIZED={0} REGISTERED_NOT_AUTHORIZED={1} UNKNOWN={2} SUSPICIOUS={3}" -f `
    $summary.authorized, $summary.registered_not_authorized, $summary.unknown, $summary.suspicious)
Write-Host ("Open alerts: {0}" -f $alertCount)
Write-Host ("Drone UID used: {0}" -f $droneUid)
Write-Host ("Unknown UID used: {0}" -f $unknownUid)
