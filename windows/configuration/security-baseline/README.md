# WinOps — Windows 11 26H2 Security Baseline application decisions

**Status:** approved policy decisions for a future post-install LGPO integration; this file is **not** an installer, and the baseline has **not** been applied to any PC by this change.

## Upstream

- Microsoft **Windows 11 v26H2 Security Baseline v2** (2026-10-08), from the official Security Compliance Toolkit.
- Reviewed original ZIP SHA-256: `369f8dad02485b3fc20be089649a29eb6432a7d0f63cef75addace9685e45d18`.
- The upstream `Scripts/Baseline-LocalInstall.ps1 -Win11NonDomainJoined` imports eight GPOs and then invokes `LGPO.exe /s ConfigFiles\DeltaForNonDomainJoined.inf /t ConfigFiles\DeltaForNonDomainJoined.txt`. **That last delta intentionally relaxes three local-account restrictions. We do not want those relaxations on WinOps.**

## Approved rule — preserve the original Microsoft restrictions

**Do not import or apply either** `DeltaForNonDomainJoined.inf` **or** `DeltaForNonDomainJoined.txt` in the WinOps configuration. Do **not** run the upstream `Baseline-LocalInstall.ps1 -Win11NonDomainJoined` unmodified.

| Policy | WinOps required value | Source in original baseline | Disallowed non-domain delta |
| --- | --- | --- | --- |
| `SeDenyNetworkLogonRight` | `*S-1-5-113` (deny network logon for local accounts) | Computer GPO `GptTmpl.inf` | Empty right / removal of the deny |
| `SeDenyRemoteInteractiveLogonRight` | `*S-1-5-113` (deny remote interactive/RDP logon for local accounts) | Computer GPO `GptTmpl.inf` | Empty right / removal of the deny |
| `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\LocalAccountTokenFilterPolicy` | `REG_DWORD 0` (keep Remote UAC filtering) | Computer GPO `registry.pol` | `REG_DWORD 1` |

`S-1-5-113` is Microsoft's well-known **Local account** SID (not the owner-specific SID). This intentionally limits remote access, including remote administration using local accounts. Local console sign-in and the selected Administrator Protection / Windows Hello elevation path remain distinct.

**Integration direction:** import only the applicable official Microsoft GPO components using the supported LGPO tool and layer separately approved WinOps overrides. Retain the three original values above; do not introduce a compensating "restore security" script, service, or additional delta. The imported settings must later be verified as **effective**; a file or registry value by itself is not a runtime acceptance proof.

## Other already approved decisions (do not reopen while importing)

- Keep `TypeOfAdminApprovalMode=2` and `ConsentPromptBehaviorEnhancedAdmin=1`: Administrator Protection + credentials **on the secure desktop**, with Windows Hello.
- Defender cloud protection enabled, but `SubmitSamplesConsent=0` (prompt; no automatic sample submissions), acknowledging reduced Block-at-First-Sight efficacy versus automatic safe/all uploads.
- Override `RDVDenyWriteAccess` to `0` so ordinary unencrypted removable media stay writable.
- Exclude domain-specific LAPS and Domain Security applicability from the standalone WinOps configuration; don't claim unsupported Credential Guard on Windows 11 Pro.
- Keep VBS, HVCI and LSA protection **without UEFI-lock at the initial post-install stage**. `windows/configuration/security-hardware.winget` is a **separate, intentionally retained, late-stage optional UEFI-lock-only overlay**, to be considered *after* the workstation is normally configured. Its presence is **not** a configuration conflict; do not automatically invoke it.
- Keep two distinct Sandbox profiles (networked and network-disabled), **clipboard enabled in both**; ordinary clipboard is distinct from disabled clipboard *history*.
- Use documented native Windows Update policies only; do not implement custom automatic-reboot blocking mechanisms.

Source-of-truth discussion/checkpoint: [Windows workstation issue #5](https://github.com/evanmih-cmd/linux/issues/5#issuecomment-6111000668); subsequent clarifications in issue comments. **Issue #9 remains the observations-only journal for actual ASUS operations.**

This file records only settled intent. Completing the full baseline policy inventory/diff, wiring the policy imports into post-install and acceptance testing remain separate implementation work.
