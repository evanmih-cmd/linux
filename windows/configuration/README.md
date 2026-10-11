# Windows post-install desired state

`workstation.winget` is the canonical post-install desired-state document.

**Mandatory ordering:** first a fully working **stock** Windows install with official hardware drivers and stable Windows Update, then an independently verified **System Restore checkpoint** of that clean Windows, and **only afterwards** DSC + LGPO custom WinOps configuration. See the authoritative [post-install guide](../POST_INSTALL_GUIDE.md). No LGPO, Administrator Protection reconfiguration or other WinOps hardening before this checkpoint.

Rules:

- Official Microsoft DSC v3 is the primary declarative engine; the canonical
  YAML uses WinGet package resources and native Windows resources.
- Prefer supported first-party/native resources.
- Do not hide arbitrary imperative PowerShell inside `Script` or `RunCommandOnSet`
  resources to make imperative configuration look declarative.
- Vendor-owned updates stay on vendor-supported channels:
  Windows Update for Windows, Google update mechanisms for Chrome.
- The VM and bare-metal workstation share this desired-state document where
  the resource semantics are hardware-independent.
- VM-only transport/bootstrap code is not part of the desired state.

**AMD RAID boot prerequisite for a future WinOps reinstall:** the authoritative [manual Windows installation runbook](../vm/deployment/README.md) must be used together with the [reconciled AMD RAID supplement](../vm/deployment/AMD_RAID_BOOT.md): separate `boot.wim` / offline deployed Windows / **externally backed-up WinRE** preparation and independent boot-critical checks. This is Windows DISM/storage servicing before post-install, **not** a DSC resource or justification for modifying the already installed ASUS. Preserve the existing Windows 11 Pro + Security Baseline path; physical observations belong in the frozen [#9](https://github.com/evanmih-cmd/linux/issues/9).

**Required manual prerequisite (physical ASUS):** before running this
post-install desired state, the owner must set an account password when
needed, enroll a working Windows Hello PIN, and verify that administrative
elevation can be approved. Administrator Protection is enabled by this
manifest; enabling it before Hello enrollment locked out the passwordless
VM account's UAC elevation after reboot. This is an installation runbook
gate, **not** a request to put credentials into unattended XML or DSC.
See [the ASUS deployment procedure](../vm/deployment/README.md#обязательный-ручной-шаг-windows-hello-до-post-install).
After the feature-configuration reboot, verify live Hello elevation and
a functional Windows Sandbox launch; registry read-back is not sufficient.

The supported execution path on both the VM and physical ASUS is native
Microsoft `dsc.exe config set --file workstation.winget --output-format json`
via `windows/vm/payload/apply-configuration.ps1`. The launcher requires the
official Microsoft DSC 3.3.0 Windows ZIP alongside the YAML and verifies its
exact SHA-256 before extracting it. This is not a custom DSC engine.
WinGet Configuration's hosted processor returned `0x80131500` for native
registry resources on this bench; direct official DSC applied all 21 resources
twice without errors and the second run made zero changes. The same canonical
document and resource definitions are used on the VM and ASUS; physical
security properties must still pass independent ASUS acceptance.

Current package baseline:

- latest stable PowerShell (`Microsoft.PowerShell`);
- Google Chrome (`Google.Chrome`) for the dedicated sensitive workload;
- Microsoft Edge (`Microsoft.Edge`) for ordinary browsing;
- official KeePass 2 (`DominikReichl.KeePass`) for KDBX databases;
- official Ledger Wallet / former Ledger Live (`LedgerHQ.LedgerLive`);
- six official Chrome Web Store wallet extensions: MetaMask, Phantom, Rabby,
  Trust Wallet, Backpack, Zerion; identities and publisher links are recorded
  in [`browser-wallets.md`](browser-wallets.md).

The Chrome extension install/update list is a single native
`Microsoft.Windows/RegistryList` DSC resource setting Google's supported
`ExtensionSettings` enterprise policy (`normal_installed` for each vetted ID;
block other user extensions). No CRX sideloading, custom scripts, or wallet
account creation. The audit verifies the **actual** Chrome Secure Preferences,
Web Store provenance, active permissions and package directories. Ledger USB
and real transaction signing remain physical ASUS acceptance checks; no seed
phrase or wallet private key is handled in the bench.

Security policy resources are added only after the selected resource/provider is
validated as supported for the target Windows build. VM policy state is never
promoted to proof of physical ASUS security behavior.

## Product-first boundary for the VM/production OS (2026-10-08)

This directory should contain *declarative configuration documents*, not
custom in-guest desired-state logic. Persistent per-logon repairs, scheduled-
task configuration agents and hand-rolled package installers are not approved.

**Access/transport is separate from configuration.** Temporary UAC elevation,
interactive logon, Guest Control, a bootstrap command wrapper, or a privileged
scheduled task may be used to invoke the supported WinGet/DSC engine during
provisioning. Prefer a supported initial-install elevated context if available.
The VM bench deliberately retains temporary elevation and credentials across
iterations; cleaning the bench is not part of the release-file guard. The
production file builder reads only explicitly approved files and rejects
VM-only AutoLogon, first-logon commands, credentials and access helpers. Owner
account enrollment is separate: the owner chooses a long emergency account
password and enrolls Windows Hello Face on the ASUS, with a distinct Hello PIN
fallback. Neither the final account password nor Hello secrets are included in
unattended media. A temporary provisioning account is not the owner's identity.
Final hardware acceptance verifies its removal. A temporary elevated task is
an access mechanism, not a competing configuration system.

Use the built-in WinGet/DSC engine and vetted resource modules when their
resource types, Windows 11 compatibility, and execution context have been
verified. A WinGet command reaching a processor is **not** evidence of
configuration convergence: inspect resource-level results and verify actual
installed programs. Do not translate failure to resolve a DSC resource
into an imperative MSI download procedure.

## International settings

- UI: en-US.
- System locale for legacy applications: en-US.
- Regional formats (UserLocale): de-DE.
- Country/GeoID: 94 (Germany).
- Time zone: W. Europe Standard Time.
- User input languages: en-US (0409:00000409) and Russian
  (0419:00000419); no German input language/layout.
- The answer-file InputLocale and UserLocale fields are separate and must
  remain independently declared.
- Windows may initialize input profiles from region/user-locale information
  on first sign-in. Validate real user state after first sign-in and updates.
- No supported Windows 11 *continuous declarative enforcement* resource for
  the exact user input-language list has passed acceptance here yet.

Excluded as an unproven substitute: legacy GlobalizationServices XML applied
using intl.cpl, which Microsoft's Windows 11 guidance does not support for
settings migrated to Windows Settings; and LanguageDsc 1.0.0.0 (2017), whose
implementation uses that legacy XML mechanism. Do not install a third-party
module solely to make this gap look solved.

## Windows Sandbox: usable offline triage

The bundled `sandbox-untrusted.wsb` is intentionally **offline**, but not
isolated from all input. Before the first launch the owner creates
`C:\Sandbox-Inbox` in Windows (the directory must exist) and puts **only
selected suspect files** there; no credentials, wallet exports or real KDBX
databases. Launching the `.wsb` opens the folder as `C:\Incoming` inside
Sandbox with read-only access. Users may inspect the file there, or copy it
inside the disposable Sandbox filesystem and run/analyse it there. The source
directory is read-only to the sandbox; changes inside Sandbox disappear when
it closes. Networking, webcam, microphone, printer and vGPU remain
disabled, **but clipboard redirection is enabled** by the owner's explicit choice.
Disable Windows clipboard *history* and cross-device sync separately, not
normal Sandbox copy/paste. Protected Client may restrict file pasting. Windows Sandbox is not a substitute for malware analysis on an
air-gapped dedicated machine, and it is not proof against all VM escape bugs.

Windows Sandbox is a Windows Pro optional feature; its runtime requires
virtualization support. The current VirtualBox/NEM bench cannot confirm a
working nested Windows Sandbox merely because the optional feature is set.
Release guard checks the `.wsb` contents fail-closed.

Microsoft's documented pattern is an offline, read-only mapped host folder:
https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-sample-configuration

## ASUS-only final UEFI Lock

The VM-compatible baseline `workstation.winget` deliberately **omits** both
`DeviceGuard\\Locked` and `HVCI\\Locked` resources: a common update/reapply
must not reset the hardware-only UEFI Lock values to zero. Its NEM guest
cannot prove real VTL1 runtime. Only the separately staged hardware overlay
sets these lock values to `1` after physical ASUS security acceptance.

`security-hardware.winget` is a separate reviewed **declarative** DSC v3
configuration for the hardware finalization stage. Its only resources set
both UEFI locks to **1**, with elevation. Production artifact guard requires
the exact overlay file and rejects a missing/mutated/VM-only substituted
version. It is staged but **not applied automatically during VM provisioning**.

Before applying the hardware overlay: boot the physical ASUS successfully,
prove VBS+HVCI are actually running, verify drivers and BitLocker/WinRE
recovery, then apply the overlay, reboot and verify effective lock behavior.
Firmware presence is available for recovery; if driver problems occur,
Microsoft documents that WinRE recovery from HVCI with UEFI lock can require
temporary Secure Boot disable in BIOS. This is a recovery cost, **not**
a disk-portability concern. Do not set `Mandatory=1` (fail-stop boot).
https://learn.microsoft.com/en-us/windows/security/hardware-security/enable-virtualization-based-protection-of-code-integrity

## Monitoring untrusted programs

Windows Sandbox has no native per-program/domain firewall activity GUI.
With Sandbox networking disabled, its virtual NIC is absent and network
monitoring cannot reliably report every desired domain. The `.wsb` profile
is for offline input inspection. Separate dynamic analysis needs a dedicated,
isolated VM plus a network enforcement point **outside** that guest, blocked
LAN access, and preserved telemetry. Safing Portmaster supports per-application
connection/domain histories and prompt/block; Sysinternals Process Monitor
shows file/registry/process behavior. Neither is yet deployed as part of the
workstation's secure-wallet host software baseline.

## Network-enabled Windows Sandbox profile

The two first-party Windows Sandbox profiles are intentionally distinct:

- `sandbox-untrusted.wsb`: offline/default, opens `C:\Incoming` in File Explorer.
- `sandbox-networked.wsb`: networking enabled, opens the built-in Windows
  Resource Monitor (`resmon.exe`) at logon. Use its Network tab to inspect
  per-process TCP connections, destinations and traffic. Open `C:\Incoming`
  separately from File Explorer to access selected files.

Both use the same read-only host `C:\Sandbox-Inbox`, Protected Client,
no microphone, webcam, printers or virtual GPU; **clipboard enabled in both**.
The networked profile intentionally supports Internet **and LAN**. This does not
make it a secure malware lab isolated from the host/network. Create the inbox
on the Windows host before use; place only disposable specimens there, never
any recovery material, wallet files, KeePass vaults, passwords or secrets.

**Important network limitation:** `<Networking>Enable</Networking>` connects
the guest through the Hyper-V default switch. This grants network connectivity
and can expose reachable local-network resources to the guest. There is NO
built-in approval prompt, host-side egress filtering, or external evidence
collection in this WSB profile. Resource Monitor runs INSIDE the guest and
cannot be trusted to capture all behavior of administrator-level malware.
This is a usability/diagnostic mode, not an adversarial malware-lab profile.
Use the offline mode for untrusted code unless isolated egress enforcement
has been implemented outside the guest. A dedicated VM/gateway is a distinct
future capability and should not be implied by this file.

Both `.wsb` profiles are on the intended production **allowlist**, and the
structural guard rejects changed networking permissions, writable mappings,
redirected devices, unexpected startup commands or swapped file identities.
The obsolete fixed-DiskID Windows Setup experiment is not the current installation
procedure. The one canonical deployment runbook now uses manual offline disk
identification/partitioning plus Microsoft DISM; Sandbox runtime still requires
an independent real Windows functional check.

Official Microsoft documentation:
https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file

## Networked Sandbox: accepted Internet + LAN behavior

The owner explicitly accepts the networked profile's Internet **and LAN** connectivity,
with normal clipboard enabled. `sandbox-networked.wsb` uses Microsoft Sandbox
`<Networking>Enable</Networking>`, Protected Client and a read-only mapped inbox,
with built-in Resource Monitor for visibility. It does **not** enforce an Internet-only
destination allowlist, prevent all host/LAN access, or guarantee malware-grade
isolation. The separate `sandbox-untrusted.wsb` disables all networking for
untrusted samples; clipboard remains enabled by the accepted compromise.
Do not add custom Hyper-V Firewall rules, a separate VM, or silent network-policy
workarounds to assert an unrequested Internet-only requirement.

**Acceptance:** on the actual ASUS launch both profiles and check their real
network access, offline isolation, read-only folder and ordinary clipboard
semantics; log limits of file paste with Protected Client. Successful XML parsing
alone is insufficient.

