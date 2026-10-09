[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ConfigurationPath,
    [string]$LogPath = 'C:\ProgramData\DesktopWindows\configuration.log'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$ProcessorPathTemporarilyEnabled = $false
$ConfigurationSucceeded = $false
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

    # Vendor-only, stable DSC package from PowerShell/DSC v3.3.0 GitHub release.
    # AppX-hosted DSC rejects Microsoft.Windows/OptionalFeatureList ("dism_dsc").
    # The one canonical manifest stays unchanged between VM and physical ASUS.
    $DscZipName = 'DSC-3.3.0-x86_64-pc-windows-msvc.zip'
    $DscZip = Join-Path (Split-Path -Parent $ConfigurationPath) $DscZipName
    $ExpectedDscSha256 = '3f8b27f648661903d066cc19d5a6e7a8c13bd07eb738d4d765ce7239619b8b5f'
    if (-not (Test-Path -LiteralPath $DscZip)) {
        throw "Official Microsoft DSC archive missing beside workstation.winget: $DscZipName"
    }
    $ActualDscSha256 = (Get-FileHash -LiteralPath $DscZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualDscSha256 -ne $ExpectedDscSha256) {
        throw 'Official Microsoft DSC archive SHA-256 mismatch. Refusing execution.'
    }
    $DscDir = Join-Path $env:ProgramData 'DesktopWindows\Tools\DSC-3.3.0'
    $ProcessorPath = Join-Path $DscDir 'dsc.exe'
    if (-not (Test-Path -LiteralPath $ProcessorPath)) {
        New-Item -ItemType Directory -Force -Path $DscDir | Out-Null
        Expand-Archive -LiteralPath $DscZip -DestinationPath $DscDir -Force
    }
    if (-not (Test-Path -LiteralPath $ProcessorPath)) {
        throw 'Verified Microsoft DSC ZIP did not contain dsc.exe'
    }
    "DSC official stable processor: $ProcessorPath; archive SHA256=$ActualDscSha256" | Add-Content $LogPath
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
            -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if (Test-Path $stdout) { Get-Content $stdout | Add-Content $LogPath }
        if (Test-Path $stderr) { Get-Content $stderr | Add-Content $LogPath }
        $code = [int]$proc.ExitCode
        ("WinGet $Step exit={0}; hex=0x{1:X8}" -f $code,$code) | Add-Content $LogPath
        return $code
    }
    # Stock read-only parser preflight. 'winget configure validate' checks
    # public module distribution and returned 1 for recognized native
    # resources; 'show' verifies the actual local document before changes.
    $showArgs = @('configure','show','-f',$ConfigurationPath,'--processor-path',$ProcessorPath,'--nowarn')
    $showCode = Invoke-WinGetConfiguration 'show' $showArgs
    # WinGet blocks custom processor paths by default as a security measure.
    # Temporarily enable only for our exact SHA-256-pinned official Microsoft
    # DSC, then always restore the original disabled setting in finally.
    $processorDisabled = $showCode -eq -1978335230 -and
        (Select-String -LiteralPath $LogPath -SimpleMatch 'ConfigurationProcessorPath' -Quiet)
    if ($processorDisabled) {
        $ProcessorPathTemporarilyEnabled = $true
        $settingsCode = Invoke-WinGetConfiguration 'enable-processor' @('settings','--enable','ConfigurationProcessorPath')
        if ($settingsCode -ne 0) {
            throw "WinGet security setting ConfigurationProcessorPath could not be temporarily enabled: $settingsCode"
        }
        $showCode = Invoke-WinGetConfiguration 'show-retry' $showArgs
    }
    if ($showCode -ne 0) { throw "WinGet configuration show/parse failed: $showCode" }
    $applyArgs = @(
        'configure','-f',$ConfigurationPath,'--processor-path',$ProcessorPath,
        '--accept-configuration-agreements','--disable-interactivity'
    )
    $code = Invoke-WinGetConfiguration 'apply' $applyArgs
    # 0x8A150069 means the configuration component is not enabled.
    # Retry ONCE after supported first-time enablement, not indefinitely.
    if ($code -eq -1978335127) {
        'WinGet Configuration not enabled; enabling official components.' | Add-Content $LogPath
        $enableCode = Invoke-WinGetConfiguration 'enable' @('configure','--enable')
        if ($enableCode -ne 0) {
            throw "Cannot enable WinGet Configuration (exit=$enableCode); Microsoft Store access may be required."
        }
        $code = Invoke-WinGetConfiguration 'retry-apply' $applyArgs
    }
    if ($code -ne 0) { throw "WinGet configure failed (exit=$code). See configuration.log and per-step stdout/stderr." }
    $ConfigurationSucceeded = $true
} catch {
    ("CONFIGURATION=FAIL: {0}" -f $_.Exception.Message) | Add-Content $LogPath
    throw
} finally {
    if ($ProcessorPathTemporarilyEnabled) {
        try {
            $settingsExit = Invoke-WinGetConfiguration 'disable-processor' @('settings','--disable','ConfigurationProcessorPath')
            if ($settingsExit -ne 0) {
                throw "Failed to restore WinGet ConfigurationProcessorPath security default (exit=$settingsExit)"
            }
        } catch {
            ("CONFIGURATION=FAIL_SECURITY_RESTORE: {0}" -f $_.Exception.Message) | Add-Content $LogPath
            throw
        }
    }
    if ($ConfigurationSucceeded) { 'CONFIGURATION=PASS' | Add-Content $LogPath }
}
