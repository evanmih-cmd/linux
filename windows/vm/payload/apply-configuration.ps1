[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ConfigurationPath,
    [string]$LogPath = 'C:\ProgramData\DesktopWindows\configuration.log'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Remove-Item $LogPath -ErrorAction SilentlyContinue
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    ("User={0}; elevated={1}; profile={2}" -f $identity.Name,$elevated,$env:USERPROFILE) | Add-Content $LogPath
    if (-not $elevated) {
        throw 'WinGet configuration requires an elevated interactive user task.'
    }
    $Package = Get-AppxPackage Microsoft.DesktopAppInstaller
    if (-not $Package) { throw 'Microsoft.DesktopAppInstaller is not registered for current user.' }
    $WinGet = Join-Path $Package.InstallLocation 'winget.exe'
    if (-not (Test-Path $WinGet)) { throw "winget.exe not found at $WinGet" }
    # --enable requires Store access; configuration processor is installed on demand.
    # v3 validation diagnostics are advisory; actual successful apply + audit are gates.
    '=== apply ===' | Add-Content $LogPath
    $stdout=$LogPath+'.stdout'; $stderr=$LogPath+'.stderr'
    Remove-Item $stdout,$stderr -ErrorAction SilentlyContinue
    $proc=Start-Process -FilePath $WinGet -ArgumentList @(
        'configure','-f',$ConfigurationPath,
        '--accept-configuration-agreements','--disable-interactivity'
    ) -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if(Test-Path $stdout){Get-Content $stdout | Add-Content $LogPath}
    if(Test-Path $stderr){Get-Content $stderr | Add-Content $LogPath}
    ("WinGet exit={0}; hex=0x{1:X8}" -f $proc.ExitCode,([uint32]$proc.ExitCode)) | Add-Content $LogPath
    if ($proc.ExitCode -ne 0) { throw "WinGet configure failed: $($proc.ExitCode)" }
    'CONFIGURATION=PASS' | Add-Content $LogPath
} catch {
    ("CONFIGURATION=FAIL: {0}" -f $_.Exception.Message) | Add-Content $LogPath
    throw
}
