param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Username = "admin",
    [string]$Password = "admin123"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

Write-Host "==> Login" -ForegroundColor Cyan
$loginBody = To-JsonString @{ username = $Username; password = $Password }
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/auth/login" -ContentType "application/json" -Body $loginBody
$authHeaders = @{ Authorization = "Bearer $($login.access_token)" }

$runId = Get-Date -Format "yyyyMMddHHmmss"
$droneUid = "POL-$runId"

Write-Host "==> Create drone" -ForegroundColor Cyan
$droneBody = To-JsonString @{
    drone_uid = $droneUid
    unit = "Alpha"
    status = "active"
}
$drone = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/drones" -Headers $authHeaders -ContentType "application/json" -Body $droneBody

Write-Host "==> Create mission with restrictive bbox policy" -ForegroundColor Cyan
$areaPolicy = '{"type":"bbox","min_lat":35,"max_lat":36,"min_lon":25,"max_lon":26,"min_alt_m":10,"max_alt_m":500}'
$now = (Get-Date).ToUniversalTime()
$missionBody = To-JsonString @{
    name = "Policy Demo $runId"
    starts_at = $now.AddMinutes(-3).ToString("o")
    ends_at = $now.AddMinutes(30).ToString("o")
    area_geom = $areaPolicy
}
$mission = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions" -Headers $authHeaders -ContentType "application/json" -Body $missionBody
$assignmentBody = To-JsonString @{
    drone_id = $drone.drone.id
    role = "recon"
}
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions/$($mission.id)/assignments" -Headers $authHeaders -ContentType "application/json" -Body $assignmentBody | Out-Null
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions/$($mission.id)/approve" -Headers $authHeaders | Out-Null

Write-Host "==> Send signed telemetry outside policy bbox" -ForegroundColor Cyan
$payload = To-JsonString @{
    lat = 41.0
    lon = 29.0
    alt_m = 120.0
    speed_mps = 10.0
    heading_deg = 85.0
    seq = 1
    source = "policy-demo"
}
$ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
$nonce = [Guid]::NewGuid().ToString()
$bodyHash = Get-HexSha256 $payload
$canonical = "$droneUid`n$ts`n$nonce`n$bodyHash"
$signature = Get-HexHmacSha256 -Secret $drone.shared_secret -Text $canonical

$telemetryHeaders = @{
    "X-Drone-Uid" = $droneUid
    "X-Ts" = $ts
    "X-Nonce" = $nonce
    "X-Signature" = $signature
    "X-Sig-Version" = "hmac-sha256-v1"
}

$result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/telemetry/ingest" -Headers $telemetryHeaders -ContentType "application/json" -Body $payload

Write-Host "==> Result" -ForegroundColor Cyan
Write-Host ("status={0} reason={1} confidence={2} signature_valid={3}" -f $result.status, $result.reason, $result.confidence, $result.signature_valid)
Write-Host ("drone_uid={0}" -f $result.drone_uid)

