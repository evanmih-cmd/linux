# VM-only transport. Collect facts with the SAME audit.ps1 used for physical ASUS.
# VirtualBox Guest Properties are the reporting channel, not an alternate audit.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RunId,
    [Parameter(Mandatory=$true)][string]$AuditPath
)
$ErrorActionPreference = 'Stop'
if ($RunId -cnotmatch '^[a-f0-9]{12}$') { throw 'Invalid audit run nonce' }
$Control = Join-Path $env:WINDIR 'System32\VBoxControl.exe'
if (-not (Test-Path -LiteralPath $Control)) { throw 'Stock VBoxControl is unavailable' }
$Prefix = "/desktopwindows/liveaudit/$RunId"
function Publish([string]$Name, [string]$Value) {
    & $Control guestproperty set "$Prefix/$Name" $Value | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "VBoxControl failed to publish $Name" }
}
try {
    Publish 'state' 'running'
    $Work = Join-Path $env:TEMP "desktop-windows-audit-$RunId"
    New-Item -ItemType Directory -Force -Path $Work | Out-Null
    $AuditLog = Join-Path $Work 'audit.log'
    # Same local report creator as on ASUS; expected policy FAIL returns 1.
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $AuditPath -Mode VM *> $AuditLog
    if ($LASTEXITCODE -notin @(0,1)) { throw "Local Windows audit launcher exited $LASTEXITCODE" }
    $LocalReportDir = Join-Path $env:ProgramData 'DesktopWindows\Audit'
    $FactsPath = Join-Path $LocalReportDir 'facts.json'
    $ResultPath = Join-Path $LocalReportDir 'result.json'
    $ReportPath = Join-Path $LocalReportDir 'report.txt'
    if (-not (Test-Path -LiteralPath $FactsPath) -or
        -not (Test-Path -LiteralPath $ResultPath) -or
        -not (Test-Path -LiteralPath $ReportPath)) {
        throw 'Common Windows auditor produced no permanent local report'
    }
    $Bytes = [System.IO.File]::ReadAllBytes($FactsPath)
    if ($Bytes.Length -eq 0 -or $Bytes.Length -gt 1048576) { throw 'Invalid audit report size' }
    # Compress with a stock .NET stream before bounded property chunks.
    $Memory = [System.IO.MemoryStream]::new()
    $Compressor = [System.IO.Compression.GZipStream]::new(
        $Memory, [System.IO.Compression.CompressionMode]::Compress, $true)
    $Compressor.Write($Bytes, 0, $Bytes.Length)
    $Compressor.Dispose()
    $Encoded = [Convert]::ToBase64String($Memory.ToArray())
    $Memory.Dispose()
    $ChunkSize = 800
    $Count = [int][Math]::Ceiling($Encoded.Length / $ChunkSize)
    if ($Count -lt 1 -or $Count -gt 120) { throw 'Invalid chunk count' }
    for ($Index = 0; $Index -lt $Count; $Index++) {
        $Start = $Index * $ChunkSize
        $Length = [Math]::Min($ChunkSize, $Encoded.Length - $Start)
        Publish ("part{0:D3}" -f $Index) $Encoded.Substring($Start, $Length)
    }
    Publish 'sha256' (Get-FileHash -Algorithm SHA256 -LiteralPath $FactsPath).Hash.ToLowerInvariant()
    Publish 'count' ([string]$Count)
    # Last write is the only completion marker; host refuses partial reports.
    Publish 'state' 'ready'
    Write-Host "LIVE_AUDIT_REPORT_PUBLISHED $RunId"
    exit 0
} catch {
    $ErrorText = $_.Exception.Message -replace '[^a-zA-Z0-9_. -]', '_'
    if ($ErrorText.Length -gt 180) { $ErrorText = $ErrorText.Substring(0,180) }
    try { Publish 'error' $ErrorText; Publish 'state' 'failed' } catch {}
    Write-Error "LIVE_AUDIT_FAILED: $ErrorText"
    exit 1
}
