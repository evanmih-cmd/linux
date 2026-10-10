# Windows 11 Pro VirtualBox bench

This harness is the Windows adaptation of the proven Linux VirtualBox harness.
It keeps the useful control-plane ideas (SOAP/WebService, deterministic VM,
snapshots, structured evidence) and deliberately drops the Linux-specific
AutoYaST/serial/scancode machinery.

## Control model

- VirtualBox is controlled only through the official SOAP/WebService API.
- `VBoxManage` is not a harness dependency.
- Windows installation uses a Windows-native `Autounattend.xml` on attached
  answer media; VirtualBox `IUnattended` is not the install mechanism.
- The official Microsoft ISO, answer-media ISO, and stock VirtualBox Guest
  Additions ISO are attached through SOAP/WebService.
- Guest Additions are VM-only transport infrastructure, not a permitted
  answer-XML extension. The original one-disk VM had Guest Control.
  The **new two-disk VM does not** currently expose usable Guest Additions/Guest
  Control, so Windows runtime audit remains blocked; keyboard scancodes are not
  a substitute for guest-command transport.
- Desktop Commander is for host-side repository/filesystem work only, not for
  injecting commands into the Windows guest.

The default WebService endpoint remains
`http://172.30.80.1:18083/` and can be overridden with `VBOX_WS_URL`.

## Canonical VM

Default VM:

```text
name:       Desktop-Windows-11-Pro
guest:      Windows11_64
firmware:   EFI64
TPM:        virtual TPM 2.0
SecureBoot: enabled with Microsoft signatures + Oracle platform key
CPU:        4 vCPU
RAM:        8 GiB
disk:       96 GiB dynamic VDI
graphics:   VBoxSVGA / 128 MiB
network:    NAT adapter, disabled during Setup/OOBE
```

Nested hardware virtualization is disabled for the installation bench by
default.  This host currently runs VirtualBox through the Windows Hyper-V/NEM
backend, where VirtualBox does not provide the native nested-virtualization
semantics needed to treat VBS/HVCI behavior as acceptance evidence.  Such
claims remain a later VM experiment and, ultimately, a bare-metal gate.

## Source ISO

Default:

```text
/home/github-runner/Windows11_Client_x64_en-us_26300_9457.iso
SHA-256:
bd4307df32bc8af33b39ccecb1174aeb345386630f89a2b86c7a4e36b55ea650
```

The hash is checked before destructive VM creation and installation.
New destructive installation is BLOCKED until the two-VDI flow and external
Guest Additions bootstrap are implemented. Existing VM/snapshot are preserved.

## VM-only credentials

The bench installation bootstrap account is `vmbench` by default. A random throwaway password is
generated once and stored outside Git at:

```text
~/.cache/desktop-windows/vbox-bench/credentials.json
```

The password is never written to run JSON, source control or issue comments.
These credentials are strictly test-bench plumbing and are not a production
account/password design.

The two-disk setup process and exact operator steps are in
[TWO_DISK_RUNBOOK.md](TWO_DISK_RUNBOOK.md). The disposable VM is separate from
the existing installed Windows VM.

**2026-10-09 updated result: first two-disk Windows desktop observed, full
acceptance NOT YET PROVEN.** Earlier stock Windows Setup attempts failed to
create a target-local ESP; do not repeat the old unallocated-space-only flow.
The successful first boot followed manual, stock WinPE DiskPart/DISM/BCDBoot/
REAgentC deployment and the same canonical password-free XML. The latest
read-only host VDI audit observed intact protected GPT/sentinel and the target
ESP/MSR/OS/WinRE layout with **17 PASS / 0 FAIL / 6 NOT_PROVABLE_ENCRYPTED**.
Because the VM remains Running, its VDI audit is provisional. Current SOAP
framebuffer is black; Shift did not wake it, Guest Additions are not ready,
and an ACPI power button did not shut Windows down. There was no hard reset.
Repeat sign-in, effective WinRE, Secure Boot and protected-disk Offline status
inside Windows remain unverified; release is still NO-GO.

## Commands

Run from `windows/vm/harness`:

```bash
python3 bench.py check
python3 bench.py iso
python3 bench.py status
python3 bench.py reset
python3 bench.py detect
python3 bench.py install
python3 bench.py reinstall
python3 bench.py resume
python3 bench.py configure
python3 bench.py audit
python3 bench.py shutdown
python3 bench.py start
python3 bench.py snapshot NAME
python3 bench.py restore NAME
python3 bench.py destroy
```

`reinstall` is the explicit destructive command; the legacy one-disk path now fails closed BEFORE reset.
`install` refuses to recreate an existing VM/disk.  The ACCEPTED FUTURE clean-install boundary
ends at the powered-off `installed-clean` snapshot:

```text
static preflight
→ exact ISO verification
→ explicit destructive VM/disk recreation (reinstall only)
→ generate throwaway-secret Autounattend.xml outside Git
→ attach official ISO + Joliet answer DVD + stock Guest Additions media
→ manual SSD1-VDI Offline via WinPE/DiskPart (two-disk bench)
→ manual selection of the target RAID LUN in interactive WinPE DiskPart
→ operator-confirmed target-only GPT partitioning, DISM image apply, BCDBoot and REAgentC using stock Microsoft tools
→ supported specialize/OOBE local-account completion from the ONE common XML copied to Windows/Panther
→ separate VirtualBox Guest Additions/Guest Control bootstrap (still to be proved)
→ working Guest Control
→ graceful shutdown
→ "installed-clean" checkpoint
```

Post-install work is a separate boundary:

```text
installed-clean
→ enable post-install network
→ interactive bootstrap profile available
→ Microsoft DSC v3 desired state (direct dsc config set)
→ structured audit
→ later post-install snapshots
```

Install-time changes (disk layout, boot path, edition, locale, OOBE) are proven
only by a clean reinstall. Post-install desired-state changes iterate from the
`installed-clean` snapshot.

A pre-existing VM with the canonical name is only destroyed if its description
contains the harness ownership marker. This prevents an accidental name
collision from deleting an unrelated VM.

## Audit

`payload/audit.ps1` produces facts only; Python evaluates them into PASS,
FAIL and NOT_PROVABLE_IN_VM (WARN is reserved for genuine optional gates).

**`python3 bench.py audit` now requires real administrator elevation inside
Windows.** The controller reuses the existing VM-only elevated interactive
Task Scheduler access mechanism to run the read-only audit, then restores its
usual WinGet launcher. The task is **retained** for later VM iterations; it
never enters production installer artifacts. No silent fallback to a
non-elevated audit or bogus PASS is allowed. An unavailable access task or
missing elevation fails execution, rather than concealing missing facts.

Most hardware-adjacent VM checks are auditable with elevation: actual guest
UEFI Secure Boot, ready TPM 2.0 specification, GPT ESP/MSR/OS/WinRE layout,
WinRE enabled/path, BitLocker protectors/status, and Administrator Protection
policy. VBS/HVCI registry policy and configured state are tested separately
from **runtime**, which the current VirtualBox Hyper-V/NEM backend cannot
faithfully prove.

Current VM-level gates include:

- non-N Windows 11 Pro;
- x64;
- exact locale/input contract, including hard failure on any German keyboard;
- real Windows Secure Boot enabled (FAIL if false or unavailable);
- virtual TPM 2.0 present, enabled, activated and ready (FAIL otherwise);
- Defender real-time protection;
- Windows Firewall on all profiles;
- installed GPT layout: target-local ESP, MSR, C:, and recovery partition;
  actual size/number chosen by stock Windows Setup, not hardcoded;
- WinRE enabled and actually located on that recovery partition;
- BitLocker OS protection On with TPM+PIN and RecoveryPassword protectors
  (currently **FAIL** in the VM: FullyEncrypted but protection Off);
- Administrator Protection mode 2 (currently **FAIL** in the VM: legacy mode 1);
- configured VBS and HVCI boot policies (runtime remains NOT_PROVABLE_IN_VM);
- Chrome installed for the sensitive workload;
- Edge installed for ordinary browsing;
- KeePass 2 installed (official KDBX-capable product, no real user database opened);
- official Ledger Wallet desktop installed (hardware Ledger USB is bare-metal gate);
- all six vetted wallet extensions actually installed in Chrome, downloaded
  from Chrome Web Store, active and free of disable reasons;
- Chrome policy contains only the six vetted IDs with other user extensions
  blocked; no unexpected profile extensions (excluding known built-in Chrome
  component and temporary download directory).

Only VBS/HVCI **runtime** and genuine physical-device claims remain separated
as VM limitations. A missing BitLocker protector or Administrator Protection
configuration is an actual FAIL, not a permission warning. A failed VM audit
must not be reported as successfully converged.

The following are always kept separate as physical ASUS gates:

- real Pluton;
- ESS Face / ACPI SDEV camera path;
- physical Secure Launch/DRTM behavior;
- physical two-SSD boot independence;
- real Ledger USB path;
- real YubiKey recovery behavior.

## Post-install desired state and payload

`../../configuration/workstation.winget` is the canonical post-install
desired-state document. `../payload/apply-configuration.ps1` is transport
glue only: it verifies the SHA-256-pinned official Microsoft DSC 3.3.0
Windows ZIP beside that document, extracts the signed upstream tools, and runs
the supported `dsc config set --file workstation.winget --output-format json`.
The native `Microsoft.WinGet/Package` resource still delegates the five package
installations to Microsoft's Windows Package Manager; registry and optional
feature resources are also first-party DSC. No second package baseline,
custom in-guest DSC implementation, or manual MSI downloader exists.

The exploratory `../payload/user-locale.ps1` is VM-only test history, **not**
an approved production desired-state resource. User locale requires a supported
product configuration path; release guards never copy harness or payload
scripts into production installation files.

### Production identity and artifact boundary

The final Windows user's long emergency/recovery account password is chosen
separately by the owner during trusted account enrollment. Daily authentication
uses Windows Hello Face with the ASUS IR camera (ESS); a distinct Hello PIN is
fallback. This account password must not be confused with the BitLocker
recovery key or the preboot startup PIN.

The same canonical XML renderer is used on the VM and ASUS, with only
per-install ephemeral identity and hostname substitutions. Neither VM nor
production XML includes AutoLogon, Guest Additions commands, disk IDs,
destructive partitioning, or an implicit first-available-disk selector.

The existing VM has Guest Additions and is used for post-install iterations.
A future fresh two-disk VM install must establish Guest Additions via
separate controlled bench plumbing (not another answer file).

The five-file production artifact allowlist is verified structurally by
harness/production_guard.py. Structural PASS is NOT release approval.
Production staging remains BLOCKED until the same manual-disk process
passes real two-disk install tests, including SSD1 sentinel preservation
and target-local ESP/WinRE. No USB writer is part of this project.

The owner creates the actual bootable USB using the verified official Microsoft
ISO; there is no project USB-writer requirement. The documented checker
`python3 release_readiness.py /path/to/latest-elevated-audit.json` produces
an explicit NO_GO/READY report with requirements 1-36, evidence per gate, and
separate preinstall, postinstall and hardware-only checks. This report does
not itself change partitions or apply guest configuration.

`../payload/audit.ps1` never prints startup PINs, Hello PINs, BitLocker
recovery passwords, vault keys, wallet seeds or service passwords.

## Environment overrides

Useful variables:

- `DESKTOP_WINDOWS_ISO`
- `DESKTOP_WINDOWS_CACHE`
- `DESKTOP_WINDOWS_VM`
- `DESKTOP_WINDOWS_VM_VCPUS`
- `DESKTOP_WINDOWS_VM_MEMORY_MIB`
- `DESKTOP_WINDOWS_VM_DISK_GIB`
- `DESKTOP_WINDOWS_VM_CREDENTIALS`
- `DESKTOP_WINDOWS_PRODUCT_KEY`
- `VBOX_WS_URL`

Activation is not required for the VM configuration proof.

### Verified native Microsoft DSC post-install result (2026-10-09)

**The earlier processor compatibility blocker is resolved.** On the existing
`Desktop-Windows-11-Pro-TwoDisk`, WinGet Configuration's AppX DSC 3.2.3
cannot invoke its bundled optional-feature resource, while WinGet Configuration
with external DSC 3.3.0 returned internal `0x80131500` for registry resources.
Direct first-party Microsoft `dsc.exe config set` works with the same canonical
`workstation.winget`; no alternate VM-specific configuration was introduced.

The common YAML now uses Microsoft `Microsoft.Windows/RegistryList` v3.3,
`Microsoft.Windows/OptionalFeatureList`, and `Microsoft.WinGet/Package`,
with native DSC `[resourceId('Microsoft.Windows/RegistryList', 'Name')]`
dependency expressions. Official DSC Windows ZIP SHA-256 is pinned as
`3f8b27f648661903d066cc19d5a6e7a8c13bd07eb738d4d765ce7239619b8b5f`.
The ASUS-only `security-hardware.winget` UEFI Lock overlay was updated to the
same official `RegistryList` type but **was not applied on the VM**; the
production guard still rejects attempts to alter UEFI Lock through the common
configuration.

**Live configuration run #1** `20261009-220702-53aa9b1c9d54`:
`CONFIGURATION=PASS`, `dsc.exe exit=0`, `hadErrors=false`, all 21 resources.
New VBS, HVCI and prerequisite registry policy keys were created as intended.

**Live configuration run #2** `20261009-220809-27ef0fa1ca4b`:
`CONFIGURATION=PASS`, `dsc.exe exit=0`, `hadErrors=false`, all 21 resources.
Every reported `changedProperties` collection was empty, proving
idempotent repeat application of the current state. Each run took about 48 s.

**Independent Windows-native audit** `20261009-220912-5bb44e9077b8`:
**27 PASS / 2 FAIL / 8 NOT_PROVABLE_IN_VM**. VBS and HVCI **registry policy**
checks now PASS; this does *not* claim working bare-metal virtualization-based
security in VirtualBox NEM. Only the two owner-deferred BitLocker protector
checks remain FAIL. Do not change audit definitions to hide them.

Actual installed packages (PowerShell 7, Chrome, Edge, KeePass 2, Ledger Wallet),
six genuine Chrome Web Store wallets and its extension policy, Windows Sandbox
feature Enabled, and en-US UI/de-DE regional formats/US+RU keyboard profiles
were previously checked in the Windows guest, and remain PASS in this audit.
Native `../payload/user-locale.ps1` fixed the owner profile in a **VM-only
exploratory step**; continuous production-safe locale convergence is not yet
a reviewed declarative resource.

Snapshot `pre-postinstall-20261009-windows11-pro-twodisk` remains available.
The current VM was not reinstalled/reset, and the original passwordless answer
DVD was restored to SATA port 4. Structural parity and audit proof in a VM
do not replace the physical ASUS tests, protected SSD1 preservation gate,
BitLocker owner enrollment, or final hardware-only acceptance.


### Post-reboot operational audit and Windows Sandbox VM limit (2026-10-10)

The earlier **27 PASS / 2 FAIL / 8 NOT_PROVABLE_IN_VM** result was
recorded **before** the first feature-servicing reboot. It was not a
functional acceptance. On reboot, Windows completed `Customizing
features` and returned to the `owner` desktop. The owner manually
configured a local password and Hello PIN (neither stored in repo/XML).
Actual Microsoft-signed PowerShell UAC elevation was authorized with
Windows Hello under `SECUREWS\ADMIN_owner`, confirming that
Administrator Protection **works in this installed VM after reboot**.

**The first post-reboot audit detected a profile-context flaw.**
Administrator Protection's short-lived elevated account had its own
`LOCALAPPDATA`, app registrations and Chrome profile. Reading those
instead of `SECUREWS\owner` falsely reported missing PowerShell 7 and
all six wallet extensions. The canonical auditor now resolves the actual
installed local `owner` SID and its loaded profile through stock WMI,
checks the owner's PowerShell MSIX with `Get-AppxPackage -User <SID>`,
and inspects only extension metadata/status inside the owner's Chrome
profile. Both Windows-native and host evaluators **fail closed** for
missing or misidentified user profiles; the ephemeral `ADMIN_owner`
is never accepted as the wallet profile. **No wallet secrets, browser
cookies or credentials are collected.**

**Verified after reboot:** Windows-native report
`20261010-091008-2b23855e4874` evaluated to **27 PASS / 3 FAIL /
8 NOT_PROVABLE_IN_VM** (38 checks). The genuine `owner` profile is
loaded, PowerShell 7.6.6 is registered there, and all six intended wallet
extensions remain present and enabled, with their Web Store indicators
and extension allowlist verified. Genuine VBS runtime status in this
guest is `VirtualizationBasedSecurityStatus=1` with no security service
actually running; registry policy PASS must never be described as
hardware VBS or HVCI runtime PASS.

**Only remaining FAILs:** the two owner-deferred BitLocker protector
checks and `windows-sandbox-feature`. Crucially,
`Containers-DisposableClientVM` is **Disabled** after feature-servicing
reboot, `RestartNeeded=False`. An interactive attempt to start
`WindowsSandbox` yielded Windows' native *cannot find program* dialog.
Therefore **Sandbox is not working in this VM** even though DSC
previously returned 21/21 successful desired-state application. The
exact Windows servicing rollback/disable reason was not established:
an exploratory read-only CBS/Event Log probe timed out without a report.
Do not invent a cause or relabel this check NOT_PROVABLE.

The physical Windows Sandbox product **requires nested hardware
virtualization to run inside a VM** (Microsoft documentation:
https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install ).
The existing VirtualBox/Hyper-V NEM bench was deliberately configured
without nested virtualization (`vm_nested_hwvirt=False`), so functional
Sandbox acceptance is an **ASUS bare-metal gate**, not something this
bench can prove. Physical acceptance must include: feature Enabled
**after reboot**, Sandbox actually launches, and its isolated environment
works. No new VM, artificial exception, disabling the Windows baseline
feature, or repetitive feature-install/reboot trial was introduced.

Observed machine after diagnostics: `Desktop-Windows-11-Pro-TwoDisk`
`Running`, Guest Additions `Desktop`, original passwordless
`Autounattend.iso` re-mounted on SATA4, snapshot count 1.
