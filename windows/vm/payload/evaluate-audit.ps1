# Common Windows-native policy evaluator for VM and ASUS.
# Needs only stock Windows PowerShell 5.1. Consumes audit.ps1 facts, no writes.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$FactsPath,
    [ValidateSet('Auto','VM','ASUS')][string]$Mode = 'Auto'
)
$ErrorActionPreference = 'Stop'
$Facts = Get-Content -LiteralPath $FactsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ComputerModel = [string]$Facts.ComputerSystem.Model
$IsVM = if ($Mode -eq 'VM') { $true } elseif ($Mode -eq 'ASUS') { $false } else {
    $ComputerModel -match 'VirtualBox|VMware|QEMU|KVM|Hyper-V|Virtual Machine'
}
$Checks = [System.Collections.Generic.List[object]]::new()
function Add-Check([string]$Name, [bool]$OK, [string]$Expected, [object]$Actual=$null, [string]$Override='') {
    $State = if ($Override) { $Override } elseif ($OK) { 'PASS' } else { 'FAIL' }
    $Checks.Add([ordered]@{
        name=$Name; status=$State; expected=$Expected; actual=$Actual
    })
}
function Set-Equal([object[]]$Left, [object[]]$Right) {
    $A = @($Left | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    $B = @($Right | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    if ($A.Count -ne $B.Count) { return $false }
    for ($I=0; $I -lt $A.Count; $I++) {
        if ($A[$I] -cne $B[$I]) { return $false }
    }
    return $true
}
function Check-Installed($Object) { return $null -ne $Object -and $Object.Installed -eq $true }

Add-Check 'audit-elevated' ($Facts.AuditContext.IsElevated -eq $true) 'Administrator context' $Facts.AuditContext
$Caption = [string]$Facts.OS.Caption
Add-Check 'windows-11-pro' ($Caption.Contains('Windows 11 Pro') -and -not $Caption.Contains('Windows 11 Pro N')) 'Windows 11 Pro non-N' $Caption
Add-Check 'x64' ([string]$Facts.OS.OSArchitecture -match '64') '64-bit' $Facts.OS.OSArchitecture
$L = $Facts.Locale
Add-Check 'ui-language-en-us' ($L.UICulture -eq 'en-US') 'en-US' $L.UICulture
Add-Check 'regional-formats-de-de' ($L.Culture -eq 'de-DE') 'de-DE' $L.Culture
Add-Check 'home-location-germany' ($L.HomeLocationGeoId -eq 94) 'Germany GeoId=94' $L.HomeLocationGeoId
Add-Check 'timezone-western-europe' ($L.TimeZoneId -eq 'W. Europe Standard Time') 'W. Europe Standard Time' $L.TimeZoneId
$Tags = @($L.UserLanguages | ForEach-Object { ([string]$_.LanguageTag).ToLowerInvariant() })
$Tips = @($L.UserLanguages | ForEach-Object { $_.InputMethodTips } | ForEach-Object { [string]$_ })
$Preload = @($L.KeyboardPreload | ForEach-Object { [string]$_ })
$KeyboardOK = ('en-us' -in $Tags) -and (('ru' -in $Tags) -or ('ru-ru' -in $Tags)) -and
    (@($Tags | Where-Object { $_ -notin @('en-us','ru','ru-ru') }).Count -eq 0) -and
    (Set-Equal $Tips @('0409:00000409','0419:00000419')) -and
    (Set-Equal $Preload @('00000409','00000419'))
Add-Check 'keyboard-layouts-us-russian-only' $KeyboardOK 'US and Russian, no German layout' $L.UserLanguages
Add-Check 'secure-boot' ($Facts.SecureBoot -eq $true) 'Secure Boot on' $Facts.SecureBoot
$T = $Facts.TPM
$TpmOK = $T.TpmPresent -eq $true -and $T.TpmReady -eq $true -and
    $T.TpmEnabled -eq $true -and $T.TpmActivated -eq $true -and
    ([string]$T.SpecVersion).Contains('2.0')
Add-Check 'tpm2-visible-ready' $TpmOK 'TPM 2.0 present, enabled and ready' $T
Add-Check 'defender-realtime' ($Facts.Defender.AntivirusEnabled -eq $true -and $Facts.Defender.RealTimeProtectionEnabled -eq $true) 'AV and realtime on' $Facts.Defender
$FW = @($Facts.Firewall)
Add-Check 'firewall-all-profiles' ($FW.Count -gt 0 -and @($FW | Where-Object { $_.Enabled -ne $true }).Count -eq 0) 'All firewall profiles enabled' $FW
$SystemDisks = @($Facts.Disks | Where-Object { $_.IsSystem -eq $true })
$DiskOK = $SystemDisks.Count -eq 1 -and $SystemDisks[0].PartitionStyle -eq 'GPT'
Add-Check 'system-disk-gpt' $DiskOK 'One GPT system disk' $SystemDisks
$TargetNumber = if ($SystemDisks.Count -eq 1) { [int]$SystemDisks[0].Number } else { -1 }
$Parts = @($Facts.Partitions | Where-Object { $_.DiskNumber -eq $TargetNumber })
$ESP = @($Parts | Where-Object { $_.GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' })
$MSR = @($Parts | Where-Object { $_.GptType -eq '{e3c9e316-0b5c-4db8-817d-f92df00215ae}' })
$Windows = @($Parts | Where-Object { $_.GptType -eq '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}' -and $_.DriveLetter -eq 'C' })
$Recovery = @($Parts | Where-Object { $_.GptType -eq '{de94bba4-06d1-4d40-a16a-bfd50179d6ac}' })
$RolesOK = $ESP.Count -eq 1 -and $MSR.Count -eq 1 -and $Windows.Count -eq 1 -and $Recovery.Count -eq 1
if ($RolesOK) {
    $RolesOK = $ESP[0].Size -gt 0 -and $MSR[0].Size -gt 0 -and
        $Windows[0].Size -gt 0 -and $Recovery[0].Size -gt 0 -and
        $ESP[0].PartitionNumber -lt $MSR[0].PartitionNumber -and
        $MSR[0].PartitionNumber -lt $Windows[0].PartitionNumber -and
        $Windows[0].PartitionNumber -lt $Recovery[0].PartitionNumber
}
Add-Check 'vm-independent-gpt-partitions' $RolesOK 'ESP / MSR / C: / WinRE in this order, target-local' $Parts
$WinRE = [string]$Facts.WinRE
Add-Check 'winre-enabled' ($WinRE -match 'Windows RE status:\s*Enabled\b') 'WinRE Enabled' $WinRE
$RecoveryPath = if ($Recovery.Count -eq 1 -and $TargetNumber -ge 0) {
    "harddisk$TargetNumber\partition$($Recovery[0].PartitionNumber)\"
} else { '' }
Add-Check 'winre-on-target-recovery' ($RecoveryPath -ne '' -and $WinRE.IndexOf($RecoveryPath, [StringComparison]::OrdinalIgnoreCase) -ge 0) 'WinRE on target recovery partition' $WinRE
Add-Check 'chrome-installed' (Check-Installed $Facts.Chrome) 'Google Chrome' $Facts.Chrome
Add-Check 'edge-installed' (Check-Installed $Facts.Edge) 'Microsoft Edge' $Facts.Edge
Add-Check 'powershell7-installed' (Check-Installed $Facts.PowerShell7) 'PowerShell 7' $Facts.PowerShell7
Add-Check 'keepass2-installed' (Check-Installed $Facts.KeePass) 'KeePass 2' $Facts.KeePass
Add-Check 'ledger-wallet-desktop' (Check-Installed $Facts.LedgerWallet) 'Ledger desktop application' $Facts.LedgerWallet
$WalletIDs = @('nkbihfbeogaeaoehlefnkodbefgpgknn',
    'bfnaelmomeimhlpmgjnjophhpkkoljpa',
    'acmacodkjbdgmoleebolmdjonilkdbch',
    'egjidjbpglichdcondbcbdnbeeppgdph',
    'aflkmfhebedbjioipglgcbcmnbpgliof',
    'klghhnkeealcohjjanjjdaeeggmfmlpl')
$Wallets = @($Facts.WalletExtensions)
$PolicyIds = @($Facts.ChromePolicy.Ids)
$WalletOK = $Wallets.Count -eq 6 -and (Set-Equal @($Wallets | ForEach-Object { $_.Id }) $WalletIDs) -and
    $Facts.ChromePolicy.ValidJson -eq $true -and
    (Set-Equal $PolicyIds @($WalletIDs + '*')) -and
    $Facts.ChromePolicy.DefaultMode -eq 'blocked' -and
    @($Facts.OtherChromeExtensionIds).Count -eq 0
if ($WalletOK) {
    foreach ($Wallet in $Wallets) {
        if ($Wallet.Installed -ne $true -or $Wallet.FromWebStore -ne $true -or
            $Wallet.ActivePermissions -ne $true -or $Wallet.InstallLocation -ne 6 -or
            @($Wallet.DisableReasons).Count -ne 0) { $WalletOK = $false; break }
    }
}
Add-Check 'chrome-wallets-verified-six' $WalletOK 'Six official enabled wallet extensions, store provenance and allowlist' $Facts.ChromePolicy
$FP = $Facts.BitLockerPolicy
$FveOK = $FP.UseAdvancedStartup -eq 1 -and $FP.EnableBDEWithNoTPM -eq 0 -and
    $FP.UseTPM -eq 2 -and $FP.UseTPMPIN -eq 2 -and
    $FP.UseTPMKey -eq 0 -and $FP.UseTPMKeyPIN -eq 0 -and $FP.MinimumPIN -eq 8
Add-Check 'bitlocker-tpm-pin-enrollment-policy' $FveOK 'TPM+PIN required, PIN >=8, no external key startup' $FP
$Sandbox = $Facts.SandboxFeature
Add-Check 'windows-sandbox-feature' ($Sandbox.Name -eq 'Containers-DisposableClientVM' -and $Sandbox.State -eq 'Enabled') 'Windows Sandbox Enabled' $Sandbox
$Bl = $Facts.BitLocker
$P = @($Bl.KeyProtectorTypes)
$Encryption = $Bl.ProtectionStatus -eq 'On' -and $Bl.VolumeStatus -eq 'FullyEncrypted'
$ImmediateOK = $Encryption -and (('Tpm' -in $P) -or ('TpmPin' -in $P)) -and ('RecoveryPassword' -in $P)
Add-Check 'bitlocker-tpm-immediate-protection' $ImmediateOK 'Encryption On, TPM protector + independent recovery' $Bl
$FlowOK = $Encryption -and ('TpmPin' -in $P) -and ('Tpm' -notin $P) -and ('RecoveryPassword' -in $P)
Add-Check 'bitlocker-vm-flow' $FlowOK 'Encryption On, TPM+PIN plus RecoveryPassword (no TPM-only)' $Bl
$DG = $Facts.DeviceGuard
$DP = $Facts.DeviceGuardPolicy
Add-Check 'vbs-boot-policy' ($DP.EnableVBS -eq 1 -and $DP.RequirePlatformSecurityFeatures -eq 1) 'VBS enabled, Secure Boot required' $DP
Add-Check 'hvci-boot-policy' ($DP.HVCIEnabled -eq 1 -and (2 -in @($DG.SecurityServicesConfigured))) 'HVCI policy and configured service 2' $DG
$VbsRunning = $DG.VirtualizationBasedSecurityStatus -eq 2
Add-Check 'vbs-runtime' $VbsRunning 'VBS runtime=2' $DG.VirtualizationBasedSecurityStatus $(if ($IsVM -and -not $VbsRunning) {'NOT_PROVABLE_IN_VM'} else {''})
$HvciRunning = 2 -in @($DG.SecurityServicesRunning)
Add-Check 'hvci-runtime' $HvciRunning 'SecurityServicesRunning contains HVCI service 2' $DG.SecurityServicesRunning $(if ($IsVM -and -not $HvciRunning) {'NOT_PROVABLE_IN_VM'} else {''})
Add-Check 'administrator-protection' ($Facts.AdministratorProtection.TypeOfAdminApprovalMode -eq 2) 'TypeOfAdminApprovalMode=2' $Facts.AdministratorProtection

# Actual hardware checks require independent owner/firmware evidence.
# On ASUS these are NOT_PROVABLE_MANUAL, never silently marked PASS.
$HardwareStatus = if ($IsVM) { 'NOT_PROVABLE_IN_VM' } else { 'NOT_PROVABLE_MANUAL' }
foreach ($Name in @('pluton-hardware','ess-face','secure-launch-drtm-physical',
                     'ledger-usb','yubikey-recovery-hardware','dual-physical-ssd-independence')) {
    Add-Check $Name $false 'Physical/manual acceptance evidence required' $null $HardwareStatus
}
$Failed = @($Checks | Where-Object { $_.status -eq 'FAIL' } | ForEach-Object { $_.name })
$Warnings = @($Checks | Where-Object { $_.status -eq 'WARN' } | ForEach-Object { $_.name })
$NotProvable = @($Checks | Where-Object { $_.status -like 'NOT_PROVABLE*' } | ForEach-Object { $_.name })
[ordered]@{
    # An ASUS run cannot be declared fully accepted when physical gates still
    # require manual or firmware evidence, even if all software checks pass.
    status = if ($Failed.Count -gt 0) { 'FAIL' } elseif (-not $IsVM -and $NotProvable.Count -gt 0) { 'INCOMPLETE' } else { 'PASS' }
    checks = @($Checks.ToArray())
    failed = $Failed
    warnings = $Warnings
    not_provable = $NotProvable
    environment = if ($IsVM) { 'VM' } else { 'PHYSICAL' }
    facts_path = $FactsPath
}
