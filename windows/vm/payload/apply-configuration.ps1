# Native official Microsoft DSC 3.3.0 transport for the ONE canonical WinGet/DSC v3 YAML.
# No handwritten resource implementation; dsc.exe invokes Microsoft.WinGet/Package,
# Microsoft.Windows/RegistryList, and Microsoft.Windows/OptionalFeatureList directly.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ConfigurationPath,
    [string]$LogPath = 'C:\ProgramData\DesktopWindows\configuration.log'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
Remove-Item -LiteralPath $LogPath -ErrorAction SilentlyContinue

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $elevated = ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    ("User={0}; elevated={1}; profile={2}" -f $identity.Name,$elevated,$env:USERPROFILE) |
        Add-Content -LiteralPath $LogPath
    if (-not $elevated) { throw 'DSC needs an elevated interactive Windows account.' }
    if (-not (Test-Path -LiteralPath $ConfigurationPath -PathType Leaf)) {
        throw "Canonical configuration is missing: $ConfigurationPath"
    }
    $archiveName = 'DSC-3.3.0-x86_64-pc-windows-msvc.zip'
    $archive = Join-Path (Split-Path -Parent $ConfigurationPath) $archiveName
    $expectedSha = '3f8b27f648661903d066cc19d5a6e7a8c13bd07eb738d4d765ce7239619b8b5f'
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
        throw "Signed Microsoft DSC archive absent beside configuration: $archiveName"
    }
    $actualSha = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha -ne $expectedSha) { throw 'DSC archive SHA-256 mismatch; refusing execution.' }
    $dscDir = Join-Path $env:ProgramData 'DesktopWindows\Tools\DSC-3.3.0'
    $dsc = Join-Path $dscDir 'dsc.exe'
    if (-not (Test-Path -LiteralPath $dsc)) {
        New-Item -ItemType Directory -Path $dscDir -Force | Out-Null
        Expand-Archive -LiteralPath $archive -DestinationPath $dscDir -Force
    }
    if (-not (Test-Path -LiteralPath $dsc -PathType Leaf)) {
        throw 'Expected official Microsoft dsc.exe was not extracted.'
    }
    "Official Microsoft DSC processor=$dsc; ZIP SHA256=$actualSha" | Add-Content -LiteralPath $LogPath
    # The WinGet Configuration host returns 0x80131500 for ALL official registry
    # resources on this VM despite the same resources working via the native
    # Microsoft DSC CLI. Do not bypass or reimplement their desired-state logic.
    # Direct dsc config set is supported: it validates and applies the same YAML.
    $stdout = "$LogPath.dsc.stdout"
    $stderr = "$LogPath.dsc.stderr"
    Remove-Item $stdout,$stderr -ErrorAction SilentlyContinue
    '=== official dsc config set ===' | Add-Content -LiteralPath $LogPath
    $quotedConfig = '"' + $ConfigurationPath.Replace('"', '') + '"'
    $proc = Start-Process -FilePath $dsc -ArgumentList @(
        'config','set','--file',$quotedConfig,'--output-format','json'
    ) -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $code = [int]$proc.ExitCode
    if (Test-Path $stdout) { Get-Content -LiteralPath $stdout | Add-Content -LiteralPath $LogPath }
    if (Test-Path $stderr) { Get-Content -LiteralPath $stderr | Add-Content -LiteralPath $LogPath }
    ("DSC exit={0}; hex=0x{1:X8}" -f $code,$code) | Add-Content -LiteralPath $LogPath
    if ($code -ne 0) { throw "Official dsc config set failed: $code; inspect native DSC output." }
    'CONFIGURATION=PASS' | Add-Content -LiteralPath $LogPath
} catch {
    ("CONFIGURATION=FAIL: {0}" -f $_.Exception.Message) | Add-Content -LiteralPath $LogPath
    throw
}
