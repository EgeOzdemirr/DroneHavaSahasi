param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Username = "admin",
    [string]$Password = "Admin-wSzi1rrquo9cCzuW",
    [int]$PointCount = 12,
    [int]$StepMs = 250
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

function New-TelemetryPacket {
    param(
        [Parameter(Mandatory = $true)][string]$DroneUid,
        [Parameter(Mandatory = $true)][string]$Secret,
        [Parameter(Mandatory = $true)][hashtable]$Payload
    )

    $ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    $nonce = [Guid]::NewGuid().ToString()
    $body = To-JsonString $Payload
    $bodyHash = Get-HexSha256 $body
    $canonical = "$DroneUid`n$ts`n$nonce`n$bodyHash"
    $signature = Get-HexHmacSha256 -Secret $Secret -Text $canonical

    return [PSCustomObject]@{
        Headers = @{
            "X-Drone-Uid" = $DroneUid
            "X-Ts" = $ts
            "X-Nonce" = $nonce
            "X-Signature" = $signature
            "X-Sig-Version" = "hmac-sha256-v1"
        }
        Body = $body
    }
}

Write-Host "==> Login" -ForegroundColor Cyan
$loginBody = To-JsonString @{ username = $Username; password = $Password }
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/auth/login" -ContentType "application/json" -Body $loginBody
$authHeaders = @{ Authorization = "Bearer $($login.access_token)" }

$runId = Get-Date -Format "yyyyMMddHHmmss"
$uid = "PLAY-$runId"

Write-Host "==> Drone oluştur: $uid" -ForegroundColor Cyan
$createDroneBody = To-JsonString @{
    drone_uid = $uid
    unit = "Alpha"
    status = "active"
}
$drone = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/drones" -Headers $authHeaders -ContentType "application/json" -Body $createDroneBody
$sharedSecret = $drone.shared_secret

Write-Host "==> Görev oluştur/ata/onayla" -ForegroundColor Cyan
$now = (Get-Date).ToUniversalTime()
$missionBody = To-JsonString @{
    name = "Single Playback Mission $runId"
    starts_at = $now.AddMinutes(-3).ToString("o")
    ends_at = $now.AddHours(1).ToString("o")
}
$mission = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions" -Headers $authHeaders -ContentType "application/json" -Body $missionBody
$assignmentBody = To-JsonString @{
    drone_id = $drone.drone.id
    role = "recon"
}
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions/$($mission.id)/assignments" -Headers $authHeaders -ContentType "application/json" -Body $assignmentBody | Out-Null
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/missions/$($mission.id)/approve" -Headers $authHeaders | Out-Null

Write-Host "==> $PointCount adet hareketli telemetri gönder" -ForegroundColor Cyan
for ($i = 0; $i -lt $PointCount; $i++) {
    $payload = @{
        lat = [math]::Round((41.001 + ($i * 0.0009)), 6)
        lon = [math]::Round((29.002 + ($i * 0.0007)), 6)
        alt_m = [math]::Round((105 + ($i * 1.2)), 2)
        speed_mps = [math]::Round((13.5 + ($i * 0.4)), 2)
        heading_deg = 82.0
        seq = $i + 1
        source = "seed-single-playback"
    }
    $packet = New-TelemetryPacket -DroneUid $uid -Secret $sharedSecret -Payload $payload
    $resp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/telemetry/ingest" -Headers $packet.Headers -ContentType "application/json" -Body $packet.Body
    if ($resp.status -ne "AUTHORIZED") {
        throw "Beklenmeyen status: $($resp.status)/$($resp.reason)"
    }
    Start-Sleep -Milliseconds $StepMs
}

Write-Host "==> Tamamlandı" -ForegroundColor Green
Write-Host "UID: $uid" -ForegroundColor Green
Write-Host "UI: $BaseUrl/ui/tactical" -ForegroundColor Yellow
Write-Host "Seçili aralık: 15dk veya 30dk, sonra Playback Yükle + Oynat" -ForegroundColor Yellow
