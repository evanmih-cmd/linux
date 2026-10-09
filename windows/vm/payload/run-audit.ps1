# Standalone one-command audit for installed Windows 11 (VM and ASUS).
# Captures facts using audit.ps1, evaluates locally using evaluate-audit.ps1,
# and always retains human-readable and JSON results on this Windows machine.
[CmdletBinding()]
param(
    [ValidateSet('Auto','VM','ASUS')][string]$Mode = 'Auto',
    [string]$FactsPath,
    [switch]$NoElevation,
    [string]$OutputRoot = (Join-Path $env:ProgramData 'DesktopWindows\Audit')
)
$ErrorActionPreference = 'Stop'
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
$IsAdmin = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    if ($NoElevation) { throw 'Cannot run a complete audit without elevation' }
    # Windows-native UAC; never change account password, UAC policy or ACL.
    $Arg = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Mode ' + $Mode
    $Child = Start-Process -FilePath 'powershell.exe' -ArgumentList $Arg -Verb RunAs -Wait -PassThru
    exit $Child.ExitCode
}
$Root = [IO.Path]::GetFullPath($OutputRoot)
$RunName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$RunDir = Join-Path (Join-Path $Root 'runs') $RunName
New-Item -ItemType Directory -Path $RunDir -Force | Out-Null
$RawPath = Join-Path $RunDir 'facts.json'
$ResultPath = Join-Path $RunDir 'result.json'
$TextPath = Join-Path $RunDir 'report.txt'
$LogPath = Join-Path $RunDir 'audit.log'
try {
    if ($FactsPath) {
        Copy-Item -LiteralPath $FactsPath -Destination $RawPath
    } else {
        & (Join-Path $PSScriptRoot 'audit.ps1') -OutputPath $RawPath *> $LogPath
    }
    if (-not (Test-Path -LiteralPath $RawPath)) { throw 'Fact collector produced no facts.json' }
    $Verdict = & (Join-Path $PSScriptRoot 'evaluate-audit.ps1') -FactsPath $RawPath -Mode $Mode
    if (-not $Verdict -or @($Verdict.checks).Count -lt 30) {
        throw 'Evaluator did not produce the full expected check set'
    }
    $Verdict | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    $Lines = [System.Collections.Generic.List[string]]::new()
    $Lines.Add('DESKTOP WINDOWS - INSTALLED SYSTEM AUDIT')
    $Lines.Add('Run: ' + $RunName)
    $Lines.Add('Computer: ' + $env:COMPUTERNAME)
    $Lines.Add('Environment: ' + $Verdict.environment)
    $Lines.Add('Verdict: ' + $Verdict.status)
    foreach ($State in @('PASS','FAIL','NOT_PROVABLE_IN_VM','NOT_PROVABLE_MANUAL','WARN')) {
        $Count = @($Verdict.checks | Where-Object { $_.status -eq $State }).Count
        if ($Count -gt 0) { $Lines.Add($State + ': ' + $Count) }
    }
    $Lines.Add('')
    $Lines.Add('CHECK RESULTS:')
    foreach ($Row in $Verdict.checks) {
        $Lines.Add(('{0,-23} {1}' -f ([string]$Row.status), ([string]$Row.name)))
        if ($Row.status -ne 'PASS') {
            $Lines.Add('    Expected: ' + [string]$Row.expected)
        }
    }
    $Lines.Add('')
    $Lines.Add('Full machine evidence: facts.json')
    $Lines.Add('Machine-readable verdicts: result.json')
    $Lines.Add('Historical run: ' + $RunDir)
    $Lines.Add('Not all hardware gates are provable in a VM or by software.')
    $Lines | Set-Content -LiteralPath $TextPath -Encoding UTF8

    New-Item -ItemType Directory -Path $Root -Force | Out-Null
    Copy-Item -LiteralPath $TextPath -Destination (Join-Path $Root 'report.txt') -Force
    Copy-Item -LiteralPath $ResultPath -Destination (Join-Path $Root 'result.json') -Force
    Copy-Item -LiteralPath $RawPath -Destination (Join-Path $Root 'facts.json') -Force
    Write-Host ('AUDIT_VERDICT ' + $Verdict.status)
    Write-Host ('AUDIT_REPORT ' + (Join-Path $Root 'report.txt'))
    Write-Host ('AUDIT_HISTORY ' + $RunDir)
    if ($Verdict.status -eq 'FAIL') { exit 1 }
    if ($Verdict.status -eq 'INCOMPLETE') { exit 4 }
    exit 0
} catch {
    $Reason = $_.Exception.Message
    ('AUDIT ERROR - NO VALID RESULT','Run: ' + $RunName, 'Reason: ' + $Reason,
     'This is a tool failure, NOT proof that Windows passed or failed.') |
        Set-Content -LiteralPath $TextPath -Encoding UTF8
    Copy-Item -LiteralPath $TextPath -Destination (Join-Path $Root 'report.txt') -Force
    Write-Error ('AUDIT_ERROR ' + $Reason)
    exit 2
}
