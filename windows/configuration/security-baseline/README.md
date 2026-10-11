# WinOps — Microsoft Security Baseline 26H2 v2

**Implementation:** precompiled native Microsoft LGPO profile for the one canonical Windows 11 Pro installation (ASUS and VM). This replaces the old decisions-only note.

## Files and tool

- `WinOps-26H2v2.lgpo.txt`: 330 effective policies, 325 Computer + 5 User.
- `WinOps-26H2v2-Computer.inf`: Microsoft Computer security settings, with original local-account remote restrictions.
- `WinOps-26H2v2-audit.csv`: 23 Microsoft advanced-audit settings.
- `APPLY.CMD`: native LGPO `/t /s /a` imports with failure propagation.
- **External official prerequisite:** `Tools/LGPO.exe`, supplied by Microsoft in [SCT LGPO.zip](https://download.microsoft.com/download/8/5/C/85C25433-A1B0-4FFA-9429-7E023E7DA8D8/LGPO.zip). Download from [Microsoft SCT](https://www.microsoft.com/en-us/download/details.aspx?id=55319), extract `LGPO_30/LGPO.exe` into this folder's `Tools` subdirectory. The baseline ZIP does not include this EXE. Do not use third-party LGPO tools.

**Provenance:** original Microsoft `Windows 11 v26H2 Security Baseline v2.zip` (8 Oct 2026), SHA-256 `369f8dad02485b3fc20be089649a29eb6432a7d0f63cef75addace9685e45d18`. Source inventory: 331 computer registry, 5 user registry, 79 security-template records (including metadata), and 23 audit rows. The result is a compiled static desired state; no stock GPO with UEFI locks is imported even transiently.

## Effective differences from Microsoft source

| Setting | Effective WinOps value |
| --- | --- |
| Administrator Protection `TypeOfAdminApprovalMode` and `ConsentPromptBehaviorEnhancedAdmin` | `2`, `1`: keep secure-desktop credential prompt |
| `SeDenyNetworkLogonRight`, `SeDenyRemoteInteractiveLogonRight` | Keep `*S-1-5-113` (deny local accounts network and RDP) |
| `LocalAccountTokenFilterPolicy` | Keep `0` (Remote UAC filtering) |
| `SubmitSamplesConsent` | `3 -> 0`: prompt before sending samples, preserve cloud protection; weaker Block at First Sight |
| `RDVDenyWriteAccess` | `1 -> 0`: removable media writable without BitLocker |
| `RunAsPPL` (two entries), `HypervisorEnforcedCodeIntegrity` | `1 -> 2`: protection on, **without UEFI lock** |
| `LsaCfgFlags`, `MachineIdentityIsolation` | Omit on standalone Pro |
| `BackupDirectory`, `ADPasswordEncryptionEnabled`, `ADBackupDSRMPassword` | Omit AD-specific LAPS |
| `WindowsFirewall\PolicyVersion` | Omit OS-owned firewall schema metadata |
| `Domain Security` GPO | Omit domain-only account/password policy |

**Never run Microsoft `Baseline-LocalInstall.ps1 -Win11NonDomainJoined` unmodified**: `DeltaForNonDomainJoined.inf/.txt` clears the two local-account logon denies and sets `LocalAccountTokenFilterPolicy=1`. Our runner imports neither delta. Other Microsoft hardening, including SmartScreen Block, Defender ASR, firewall and auditing, remains.

## Application order / checkpoint prerequisite

**Do not apply this native LGPO baseline during OOBE or initial stock Windows setup.** First complete supported Windows device drivers and stable Windows Update including required owner-controlled reboots. **Then create and verify a System Restore point of the working, unmodified Windows** (see [canonical post-install guide](../../POST_INSTALL_GUIDE.md)). Only after that checkpoint invoke the shared DSC + LGPO launcher. Optional UEFI-lock remains a separate deferred decision.

## Offline USB post-install integration

Copy this whole directory to `U:\PostInstall\security-baseline\`, including official `Tools\LGPO.exe`. The standard launcher `U:\PostInstall\apply-configuration.ps1 -ConfigurationPath U:\PostInstall\workstation.winget` runs Microsoft DSC then this native LGPO stage. Administrator manually configures password and Windows Hello **before** running it. A missing dependency or nonzero LGPO exit is a configuration failure. No reboot is initiated by APPLY.CMD; reboot/functional acceptance is separate.

`windows/configuration/security-hardware.winget` is a **separate, unchanged, optional UEFI-lock overlay for later**. This stage must never invoke it. Sandbox clipboard policy is in the two existing `.wsb` profiles and separate from disabled Windows clipboard history.

Scope: security baseline implementation, not proof of live WinOps behavior. No changes to ASUS, its disks or recovery/BitLocker keys occurred here. Decision record: [issue #5](https://github.com/evanmih-cmd/linux/issues/5); issue #9 remains observation-only.
