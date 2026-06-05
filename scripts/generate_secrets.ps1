param(
    [int]$JwtLength = 48,
    [int]$BridgeTokenLength = 40,
    [int]$BootstrapPasswordLength = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-RandomString {
    param(
        [Parameter(Mandatory = $true)][int]$Length,
        [string]$Alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    $bytes = New-Object byte[] ($Length)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    $chars = for ($i = 0; $i -lt $Length; $i++) {
        $Alphabet[$bytes[$i] % $Alphabet.Length]
    }
    return -join $chars
}

function New-UrlSafeBase64Key {
    param([int]$ByteCount = 32)
    $bytes = New-Object byte[] ($ByteCount)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return ([Convert]::ToBase64String($bytes)).Replace('+', '-').Replace('/', '_')
}

$jwtSecret = New-RandomString -Length $JwtLength
$bridgeToken = New-RandomString -Length $BridgeTokenLength
$bootstrapPassword = New-RandomString -Length $BootstrapPasswordLength
$masterKey = New-UrlSafeBase64Key -ByteCount 32

Write-Host "Generated secrets (copy to .env):" -ForegroundColor Cyan
Write-Host "JWT_SECRET_KEY=$jwtSecret"
Write-Host "BRIDGE_SOURCE_TOKEN=$bridgeToken"
Write-Host "MASTER_KEY=$masterKey"
Write-Host "BOOTSTRAP_ADMIN_PASSWORD=$bootstrapPassword"
