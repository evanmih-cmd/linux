# VM-only report transport for the canonical WinGet/DSC configuration.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunId)
$ErrorActionPreference='Stop'
if($RunId -cnotmatch '^[a-f0-9]{12}$'){throw 'Invalid run ID'}
$admin=([Security.Principal.WindowsPrincipal]::new(
  [Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not $admin){
    $child=Start-Process -FilePath powershell.exe -ArgumentList (
      '-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -RunId '+$RunId
    ) -Verb RunAs -Wait -PassThru
    exit $child.ExitCode
}
$control=Join-Path $env:WINDIR 'System32\VBoxControl.exe'
$prefix="/desktopwindows/postinstall/$RunId"
function Put([string]$name,[string]$value){
    & $control guestproperty set "$prefix/$name" $value | Out-Null
    if($LASTEXITCODE -ne 0){throw "GuestProperty failed: $name"}
}
try {
    Put state running
    $source=Join-Path $PSScriptRoot 'apply-configuration.ps1'
    $manifest=Join-Path $PSScriptRoot 'workstation.winget'
    try {
        & $source -ConfigurationPath $manifest
    } catch {
        Write-Host ("CONFIG_RUNNER_CAUGHT: "+$_.Exception.Message)
    }
    $log='C:\ProgramData\DesktopWindows\configuration.log'
    if(Test-Path $log){$bytes=[IO.File]::ReadAllBytes($log)}
    else {$bytes=[Text.Encoding]::UTF8.GetBytes('ERROR: configuration.log not produced')}
    if($bytes.Length -gt 524288){throw 'Configuration log unexpectedly large'}
    $text=[Text.Encoding]::UTF8.GetString($bytes)
    $passed=$text.Contains('CONFIGURATION=PASS') -and
        -not $text.Contains('CONFIGURATION=FAIL')
    $mem=[IO.MemoryStream]::new()
    $zip=[IO.Compression.GZipStream]::new($mem,[IO.Compression.CompressionMode]::Compress,$true)
    $zip.Write($bytes,0,$bytes.Length);$zip.Dispose()
    $encoded=[Convert]::ToBase64String($mem.ToArray());$mem.Dispose()
    $chunksize=800;$count=[int][Math]::Ceiling($encoded.Length/$chunksize)
    if($count -lt 1 -or $count -gt 120){throw 'Too many guestproperty chunks'}
    for($i=0;$i -lt $count;$i++){
        $start=$i*$chunksize
        $length=[Math]::Min($chunksize,$encoded.Length-$start)
        Put ("part{0:D3}" -f $i) $encoded.Substring($start,$length)
    }
    $sha=[Security.Cryptography.SHA256]::Create()
    try{$hash=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}
    finally{$sha.Dispose()}
    Put sha256 $hash
    Put count ([string]$count)
    Put outcome $(if($passed){'PASS'}else{'FAIL'})
    Put state ready
    Write-Host "DESKTOP_POSTINSTALL_REPORT_READY $RunId"
    if($passed){exit 0}else{exit 1}
} catch {
    try{
        $msg=$_.Exception.Message -replace '[^a-zA-Z0-9_. -]','_'
        if($msg.Length -gt 180){$msg=$msg.Substring(0,180)}
        Put error $msg
        Put state failed
    }catch{}
    Write-Host "DESKTOP_POSTINSTALL_REPORT_FAILED $RunId"
    exit 2
}
