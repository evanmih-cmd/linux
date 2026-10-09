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
    # Microsoft WinGet Configuration is an opt-in component, not automatically
    # enabled by installing WinGet. Use only Microsoft's supported enable path.
    # This may require Microsoft Store access (including network availability).
    # A signed WinGet HRESULT MUST NOT be cast directly to UInt32 on PS 5.1.
    function Invoke-WinGetConfiguration([string]$Step, [string[]]$Arguments) {
        $stdout = "$LogPath.$Step.stdout"
        $stderr = "$LogPath.$Step.stderr"
        Remove-Item $stdout,$stderr -ErrorAction SilentlyContinue
        "=== $Step ===" | Add-Content $LogPath
        $proc = Start-Process -FilePath $WinGet -ArgumentList $Arguments `
            -Wait -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if (Test-Path $stdout) { Get-Content $stdout | Add-Content $LogPath }
        if (Test-Path $stderr) { Get-Content $stderr | Add-Content $LogPath }
        $code = [int]$proc.ExitCode
        ("WinGet $Step exit={0}; hex=0x{1:X8}" -f $code,$code) | Add-Content $LogPath
        return $code
    }
    $applyArgs = @(
        'configure','-f',$ConfigurationPath,
        '--accept-configuration-agreements','--disable-interactivity'
    )
    $code = Invoke-WinGetConfiguration 'apply' $applyArgs
    # 0x8A150069 means the configuration component is not enabled.
    # Retry ONCE after supported first-time enablement, not indefinitely.
    if ($code -eq -1978335127) {
        'WinGet Configuration not enabled; enabling official components.' | Add-Content $LogPath
        $enableCode = Invoke-WinGetConfiguration 'enable' @('configure','--enable','--disable-interactivity')
        if ($enableCode -ne 0) {
            throw "Cannot enable WinGet Configuration (exit=$enableCode); Microsoft Store access may be required."
        }
        $code = Invoke-WinGetConfiguration 'retry-apply' $applyArgs
    }
    if ($code -ne 0) { throw "WinGet configure failed (exit=$code). See configuration.log and per-step stdout/stderr." }
    'CONFIGURATION=PASS' | Add-Content $LogPath
} catch {
    ("CONFIGURATION=FAIL: {0}" -f $_.Exception.Message) | Add-Content $LogPath
    throw
}
