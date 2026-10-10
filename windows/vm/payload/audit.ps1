[CmdletBinding()]
param(
    [string]$OutputPath = 'C:\ProgramData\DesktopWindows\audit.json'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$CurrentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$CurrentPrincipal = [Security.Principal.WindowsPrincipal]::new($CurrentIdentity)
$IsElevated = $CurrentPrincipal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

function Try-Value {
    param([scriptblock]$Script)
    try { & $Script } catch { $null }
}

$Os = Get-CimInstance Win32_OperatingSystem
$ComputerSystem = Get-CimInstance Win32_ComputerSystem
$SecureBoot = Try-Value { [bool](Confirm-SecureBootUEFI) }
$Tpm = Try-Value { Get-Tpm }
$SandboxFeature = Try-Value { Get-WindowsOptionalFeature -Online -FeatureName 'Containers-DisposableClientVM' }
$FVEPolicy = Try-Value { Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\FVE' }
$TpmDetails = Try-Value {
    Get-CimInstance -Namespace 'root\cimv2\Security\MicrosoftTpm' -ClassName Win32_Tpm
}

$LanguageList = Get-WinUserLanguageList
$UserLanguages = @(
    foreach ($Language in $LanguageList) {
        [ordered]@{
            LanguageTag = [string]$Language.LanguageTag
            InputMethodTips = @(
                $Language.InputMethodTips |
                    ForEach-Object { [string]$_ }
            )
        }
    }
)
$KeyboardPreloadKey = Try-Value {
    Get-ItemProperty 'HKCU:\Keyboard Layout\Preload'
}
$KeyboardPreload = @(
    if ($KeyboardPreloadKey) {
        $KeyboardPreloadKey.PSObject.Properties |
            Where-Object { $_.Name -match '^[0-9]+$' } |
            Sort-Object { [int]$_.Name } |
            ForEach-Object { [string]$_.Value }
    }
)
$HomeLocation = Try-Value { Get-WinHomeLocation }
$Locale = [ordered]@{
    Culture = [string](Get-Culture).Name
    UICulture = [string](Get-UICulture).Name
    HomeLocationGeoId = Try-Value { [int]$HomeLocation.GeoId }
    TimeZoneId = [string](Get-TimeZone).Id
    UserLanguages = $UserLanguages
    KeyboardPreload = $KeyboardPreload
}

$BitLocker = $null
if (Get-Command Get-BitLockerVolume -ErrorAction SilentlyContinue) {
    $Bl = Try-Value { Get-BitLockerVolume -MountPoint 'C:' }
    if ($Bl) {
        $BitLocker = [ordered]@{
            VolumeStatus = [string]$Bl.VolumeStatus
            ProtectionStatus = [string]$Bl.ProtectionStatus
            EncryptionMethod = [string]$Bl.EncryptionMethod
            EncryptionPercentage = [int]$Bl.EncryptionPercentage
            KeyProtectorTypes = @(
                $Bl.KeyProtector | ForEach-Object { [string]$_.KeyProtectorType }
            )
        }
    }
}

$Dg = Try-Value { Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard }
$VbsPolicy = Try-Value { Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard' }
$HvciPolicy = Try-Value { Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity' }
$DeviceGuard = if ($Dg) {
    [ordered]@{
        VirtualizationBasedSecurityStatus = [int]$Dg.VirtualizationBasedSecurityStatus
        SecurityServicesConfigured = @($Dg.SecurityServicesConfigured | ForEach-Object { [int]$_ })
        SecurityServicesRunning = @($Dg.SecurityServicesRunning | ForEach-Object { [int]$_ })
        AvailableSecurityProperties = @($Dg.AvailableSecurityProperties | ForEach-Object { [int]$_ })
        RequiredSecurityProperties = @($Dg.RequiredSecurityProperties | ForEach-Object { [int]$_ })
    }
} else { $null }

$Mp = Try-Value { Get-MpComputerStatus }
$Defender = if ($Mp) {
    [ordered]@{
        AntivirusEnabled = [bool]$Mp.AntivirusEnabled
        AMServiceEnabled = [bool]$Mp.AMServiceEnabled
        RealTimeProtectionEnabled = [bool]$Mp.RealTimeProtectionEnabled
        AntispywareEnabled = [bool]$Mp.AntispywareEnabled
        AntivirusSignatureVersion = [string]$Mp.AntivirusSignatureVersion
    }
} else { $null }

$Firewall = @(
    Get-NetFirewallProfile | Sort-Object Name | ForEach-Object {
        [ordered]@{
            Name = [string]$_.Name
            Enabled = [bool]$_.Enabled
            DefaultInboundAction = [string]$_.DefaultInboundAction
            DefaultOutboundAction = [string]$_.DefaultOutboundAction
        }
    }
)

$Disks = @(
    Get-Disk | Sort-Object Number | ForEach-Object {
        [ordered]@{
            Number = [int]$_.Number
            FriendlyName = [string]$_.FriendlyName
            BusType = [string]$_.BusType
            PartitionStyle = [string]$_.PartitionStyle
            Size = [uint64]$_.Size
            IsBoot = [bool]$_.IsBoot
            IsSystem = [bool]$_.IsSystem
            IsOffline = [bool]$_.IsOffline
        }
    }
)

$Partitions = @(
    Get-Partition | Sort-Object DiskNumber,PartitionNumber | ForEach-Object {
        [ordered]@{
            DiskNumber = [int]$_.DiskNumber
            PartitionNumber = [int]$_.PartitionNumber
            DriveLetter = [string]$_.DriveLetter
            Type = [string]$_.Type
            GptType = [string]$_.GptType
            Size = [uint64]$_.Size
            IsBoot = [bool]$_.IsBoot
            IsSystem = [bool]$_.IsSystem
        }
    }
)

$WinRE = Try-Value { (& reagentc.exe /info 2>&1 | Out-String).Trim() }

$ChromePath = Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
$Chrome = if (Test-Path $ChromePath) {
    [ordered]@{
        Installed = $true
        Version = [string](Get-Item $ChromePath).VersionInfo.ProductVersion
        Path = $ChromePath
    }
} else {
    [ordered]@{ Installed = $false; Version = $null; Path = $ChromePath }
}

$EdgePath = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path $EdgePath)) {
    $EdgePath = Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'
}
$Edge = if (Test-Path $EdgePath) {
    [ordered]@{
        Installed = $true
        Version = [string](Get-Item $EdgePath).VersionInfo.ProductVersion
        Path = $EdgePath
    }
} else {
    [ordered]@{ Installed = $false; Version = $null; Path = $EdgePath }
}

# KeePass installer location varies by package/build; verify the actual
# executable in the vendor's standard Program Files directories.
$KeePassCandidates = @(
    (Join-Path $env:ProgramFiles 'KeePass Password Safe 2\KeePass.exe')
    (Join-Path ${env:ProgramFiles(x86)} 'KeePass Password Safe 2\KeePass.exe')
    (Join-Path ${env:ProgramFiles(x86)} 'KeePass2x\KeePass.exe')
)
$KeePassPath = $KeePassCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
$KeePass = [ordered]@{
    Installed = [bool]$KeePassPath
    Version = if ($KeePassPath) { [string](Get-Item -LiteralPath $KeePassPath).VersionInfo.ProductVersion } else { $null }
    Path = if ($KeePassPath) { [string]$KeePassPath } else { $null }
}

$LedgerWalletPath = 'C:\Program Files\Ledger Wallet\Ledger Wallet.exe'
$LedgerWallet = [ordered]@{
    Installed = (Test-Path $LedgerWalletPath)
    Version = if (Test-Path $LedgerWalletPath) { (Get-Item $LedgerWalletPath).VersionInfo.ProductVersion } else { $null }
    Path = $LedgerWalletPath
}

# Administrator Protection elevates using an ephemeral ADMIN_owner identity.
# Audit the canonical installed local owner's actual SID/profile, never the
# current admin token's HKCU/LOCALAPPDATA. Only package/extension metadata and
# state flags are collected. No passwords, cookies, wallet data or seeds.
$CanonicalOwnerName = 'owner'
$OwnerAccount = Try-Value {
    Get-CimInstance Win32_UserAccount -Filter "Name='owner' AND LocalAccount=True"
}
$OwnerSid = if ($OwnerAccount) { [string]$OwnerAccount.SID } else { $null }
$OwnerUserProfile = if ($OwnerSid) {
    Try-Value { Get-CimInstance Win32_UserProfile -Filter "SID='$OwnerSid'" }
} else { $null }
$OwnerProfilePath = if ($OwnerUserProfile) {
    [string]$OwnerUserProfile.LocalPath
} else { $null }
$OwnerProfileValid = [bool](
    $OwnerAccount -and $OwnerSid -and $OwnerProfilePath -and
    (Split-Path -Path $OwnerProfilePath -Leaf) -ieq $CanonicalOwnerName -and
    (Test-Path -LiteralPath $OwnerProfilePath -PathType Container)
)
$OwnerLocalAppData = if ($OwnerProfileValid) {
    Join-Path $OwnerProfilePath 'AppData\Local'
} else { $null }
$OwnerProfileEvidence = [ordered]@{
    Name = $CanonicalOwnerName
    SID = $OwnerSid
    Path = $OwnerProfilePath
    Loaded = if ($OwnerUserProfile) { [bool]$OwnerUserProfile.Loaded } else { $false }
    Resolved = $OwnerProfileValid
}

# Audit only extension IDs, publisher store provenance flags and enablement
# indicators. Never serialize any wallet settings, keys or profile secrets.
$RequiredWalletIds = @(
    'nkbihfbeogaeaoehlefnkodbefgpgknn', # MetaMask
    'bfnaelmomeimhlpmgjnjophhpkkoljpa', # Phantom
    'acmacodkjbdgmoleebolmdjonilkdbch', # Rabby
    'egjidjbpglichdcondbcbdnbeeppgdph', # Trust Wallet
    'aflkmfhebedbjioipglgcbcmnbpgliof', # Backpack
    'klghhnkeealcohjjanjjdaeeggmfmlpl'  # Zerion
)
$ChromePolicyPath = 'HKLM:\SOFTWARE\Policies\Google\Chrome'
$PolicyString = Try-Value {
    [string](Get-ItemProperty -Path $ChromePolicyPath -Name ExtensionSettings -ErrorAction Stop).ExtensionSettings
}
$ChromePolicyObject = Try-Value { $PolicyString | ConvertFrom-Json -ErrorAction Stop }
$ChromePolicy = [ordered]@{
    ValidJson = [bool]$ChromePolicyObject
    Ids = @(
        if ($ChromePolicyObject) {
            $ChromePolicyObject.PSObject.Properties.Name | Sort-Object
        }
    )
    DefaultMode = if ($ChromePolicyObject) {
        [string]$ChromePolicyObject.PSObject.Properties['*'].Value.installation_mode
    } else { $null }
}

$ChromeDefaultProfile = if ($OwnerLocalAppData) {
    Join-Path $OwnerLocalAppData 'Google\Chrome\User Data\Default'
} else { $null }
$SecurePrefPath = if ($ChromeDefaultProfile) {
    Join-Path $ChromeDefaultProfile 'Secure Preferences'
} else { $null }
$SecurePrefObject = Try-Value {
    if (-not $SecurePrefPath) { return $null }
    Get-Content -Raw -Path $SecurePrefPath -ErrorAction Stop |
        ConvertFrom-Json -ErrorAction Stop
}
$ExtensionDir = if ($ChromeDefaultProfile) { Join-Path $ChromeDefaultProfile 'Extensions' } else { $null }
$WalletExtensions = @(
    foreach ($Id in $RequiredWalletIds) {
        $Saved = if ($SecurePrefObject) {
            $SecurePrefObject.extensions.settings.PSObject.Properties[$Id].Value
        } else { $null }
        $Folder = if ($ExtensionDir) { Join-Path $ExtensionDir $Id } else { $null }
        $Versions = @(
            if ($Folder -and (Test-Path -LiteralPath $Folder)) {
                Get-ChildItem -Path $Folder -Directory -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty Name
            }
        )
        [ordered]@{
            Id = $Id
            Installed = ($Versions.Count -gt 0) -and [bool]$Saved
            Versions = $Versions
            Name = if ($Saved) { [string]$Saved.manifest.name } else { $null }
            FromWebStore = if ($Saved) { [bool]$Saved.from_webstore } else { $false }
            InstallLocation = if ($Saved) { $Saved.location } else { $null }
            ActivePermissions = if ($Saved) { [bool]$Saved.active_permissions } else { $false }
            DisableReasons = @(if ($Saved) { $Saved.disable_reasons })
        }
    }
)
$OtherChromeExtensionIds = @(
    if ($ExtensionDir -and (Test-Path -LiteralPath $ExtensionDir)) {
        Get-ChildItem -Path $ExtensionDir -Directory -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -notin $RequiredWalletIds -and
                $_.Name -notin @('Temp', 'nmmhkkegccagdldgiimedpiccmgmieda')
            } | Select-Object -ExpandProperty Name
    }
)

# PowerShell 7.6+ WinGet defaults to Microsoft's signed MSIX package.
# Accept a registered MSIX + user alias OR a vendor MSI installation.
$PowerShellMSIX = if ($OwnerProfileValid) {
    Try-Value { Get-AppxPackage -Name Microsoft.PowerShell -User $OwnerSid }
} else { $null }
$PowerShellMSIPath = Join-Path $env:ProgramFiles 'PowerShell\7\pwsh.exe'
$PowerShellAlias = if ($OwnerLocalAppData) {
    Join-Path $OwnerLocalAppData 'Microsoft\WindowsApps\pwsh.exe'
} else { $null }
if ($OwnerProfileValid -and $PowerShellMSIX -and
    $PowerShellAlias -and (Test-Path -LiteralPath $PowerShellAlias)) {
    $PowerShell7 = [ordered]@{
        Installed = $true
        Method = 'MSIX'
        Version = [string]$PowerShellMSIX.Version
        Path = [string]$PowerShellMSIX.InstallLocation
    }
} elseif ($OwnerProfileValid -and (Test-Path -LiteralPath $PowerShellMSIPath)) {
    $PowerShell7 = [ordered]@{
        Installed = $true
        Method = 'MSI'
        Version = [string](Get-Item $PowerShellMSIPath).VersionInfo.ProductVersion
        Path = $PowerShellMSIPath
    }
} else {
    $PowerShell7 = [ordered]@{
        Installed = $false
        Method = $null
        Version = $null
        Path = $null
    }
}

$PendingReboot = [bool](
    (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or
    (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
)

$Uac = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
$AdminProtection = [ordered]@{
    EnableLUA = Try-Value { [int]$Uac.EnableLUA }
    TypeOfAdminApprovalMode = Try-Value { [int]$Uac.TypeOfAdminApprovalMode }
    ConsentPromptBehaviorAdmin = Try-Value { [int]$Uac.ConsentPromptBehaviorAdmin }
}

$Facts = [ordered]@{
    Schema = 1
    CapturedAt = (Get-Date).ToUniversalTime().ToString('o')
    AuditContext = [ordered]@{
        User = [string]$CurrentIdentity.Name
        IsElevated = [bool]$IsElevated
    }
    ComputerName = $env:COMPUTERNAME
    OS = [ordered]@{
        Caption = [string]$Os.Caption
        Version = [string]$Os.Version
        BuildNumber = [string]$Os.BuildNumber
        OSArchitecture = [string]$Os.OSArchitecture
        ProductType = [int]$Os.ProductType
    }
    ComputerSystem = [ordered]@{
        Manufacturer = [string]$ComputerSystem.Manufacturer
        Model = [string]$ComputerSystem.Model
    }
    Locale = $Locale
    SecureBoot = $SecureBoot
    TPM = if ($Tpm) {
        [ordered]@{
            TpmPresent = [bool]$Tpm.TpmPresent
            TpmReady = [bool]$Tpm.TpmReady
            TpmEnabled = [bool]$Tpm.TpmEnabled
            TpmActivated = [bool]$Tpm.TpmActivated
            ManufacturerIdTxt = [string]$Tpm.ManufacturerIdTxt
            ManufacturerVersion = [string]$Tpm.ManufacturerVersion
            SpecVersion = if ($TpmDetails) { [string]$TpmDetails.SpecVersion } else { $null }
        }
    } else { $null }
    BitLocker = $BitLocker
    BitLockerPolicy = [ordered]@{
        UseAdvancedStartup = Try-Value { [int]$FVEPolicy.UseAdvancedStartup }
        EnableBDEWithNoTPM = Try-Value { [int]$FVEPolicy.EnableBDEWithNoTPM }
        UseTPM = Try-Value { [int]$FVEPolicy.UseTPM }
        UseTPMPIN = Try-Value { [int]$FVEPolicy.UseTPMPIN }
        UseTPMKey = Try-Value { [int]$FVEPolicy.UseTPMKey }
        UseTPMKeyPIN = Try-Value { [int]$FVEPolicy.UseTPMKeyPIN }
        MinimumPIN = Try-Value { [int]$FVEPolicy.MinimumPIN }
    }
    SandboxFeature = if ($SandboxFeature) {
        [ordered]@{
            Name = [string]$SandboxFeature.FeatureName
            State = [string]$SandboxFeature.State
            RestartNeeded = [string]$SandboxFeature.RestartNeeded
        }
    } else { $null }
    DeviceGuard = $DeviceGuard
    DeviceGuardPolicy = [ordered]@{
        EnableVBS = Try-Value { [int]$VbsPolicy.EnableVirtualizationBasedSecurity }
        RequirePlatformSecurityFeatures = Try-Value { [int]$VbsPolicy.RequirePlatformSecurityFeatures }
        VBSLocked = Try-Value { [int]$VbsPolicy.Locked }
        HVCIEnabled = Try-Value { [int]$HvciPolicy.Enabled }
        HVCILocked = Try-Value { [int]$HvciPolicy.Locked }
    }
    Defender = $Defender
    Firewall = $Firewall
    Disks = $Disks
    Partitions = $Partitions
    WinRE = $WinRE
    AdministratorProtection = $AdminProtection
    Chrome = $Chrome
    Edge = $Edge
    PowerShell7 = $PowerShell7
    KeePass = $KeePass
    LedgerWallet = $LedgerWallet
    ChromePolicy = $ChromePolicy
    OwnerProfile = $OwnerProfileEvidence
    WalletExtensions = $WalletExtensions
    OtherChromeExtensionIds = $OtherChromeExtensionIds
    PendingReboot = $PendingReboot
}

$Directory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $Directory | Out-Null
$Facts | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $OutputPath
