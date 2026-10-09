# Windows security workstation — architecture

## Status and authority

This document defines the current technical architecture for the Windows security workstation.

The authoritative product requirements are in
[`BUSINESS_REQUIREMENTS.md`](BUSINESS_REQUIREMENTS.md). If this architecture
conflicts with a business requirement, the requirement wins and this document
must change.

The previous Linux portable-workstation design remains preserved under
`portable/` as a proven fallback and research record. It is no longer the
production architecture for this workstation.

The architecture is deliberately **Product First** and **Economy First**:

- **Product First** means supported product mechanisms are evaluated before we
  build substitutes. It does not mean custom work is forbidden.
- **Economy First** means total lifecycle cost matters: implementation effort,
  repeated administration, recovery burden, debugging time, hardware cost,
  update burden and expected failure cost. It does not mean "fewest
  components at any price".
- A built-in feature does not win merely because it is built in; it wins when
  it satisfies the requirements at lower lifecycle cost.
- Custom code is acceptable when the platform has a real gap and the custom
  component can be kept narrow, auditable and cheaper than the alternatives.
- Preview/beta/test-only functionality is not a production dependency unless a
  requirement explicitly accepts that risk.

The architecture intentionally separates:

1. **software/configuration proof** developed in the VirtualBox bench (#6);
2. **hardware/security-boundary proof** performed on the ASUS (#5).

A VM result is never promoted into evidence for a hardware-specific claim that
the VM cannot faithfully model.

## Architecture decision

The production platform is **Windows 11 Pro on the second internal SSD of the
ASUS TUF A14 FA401EA**.

The key product change from the Linux design is intentional:

- portability of the complete OS between arbitrary hosts is no longer a
  requirement;
- the primary ASUS may be part of the trust architecture;
- the workstation is treated primarily as a **user identity, credential and
  authorization endpoint** for cloud and high-value services;
- the ordinary desktop OS is not treated as the only security boundary;
- long-lived secrets should live behind independent hardware/VBS trust
  boundaries where the platform supports that model.

This makes supported Windows mechanisms such as BitLocker, TPM/Pluton,
Windows Hello, Enhanced Sign-in Security, Virtualization-Based Security,
Hypervisor-protected Code Integrity and VBS enclaves first-class architectural
building blocks instead of recreating equivalents in the desktop OS.

## Primary hardware and workload

Primary machine:

- ASUS TUF A14 FA401EA;
- AMD Ryzen AI MAX+ 392 / Zen 5;
- two internal M.2 slots;
- built-in ASUS FHD webcam and IR camera;
- Microsoft Pluton security processor present on the platform;
- existing Windows 11 Home installation on SSD1;
- Windows 11 Pro production installation on SSD2.

The workload is intentionally narrow:

- browser-centric access to cloud services;
- password/passkey and other credential use;
- crypto/wallet extensions;
- Ledger-backed transaction signing;
- other potentially irreversible high-value actions;
- ordinary administration required to keep the workstation secure and usable.

The workstation does **not** need to be optimized as a generic local compute
server. Cloud storage and remote services may hold the bulk of working data.
The local machine's distinctive value is its ability to:

- establish user identity;
- protect device-bound secrets;
- authorize use of credentials;
- provide trusted or stronger-than-normal execution domains;
- mediate access to external hardware roots of trust.

## Selected Windows edition and install language

Production edition:

- **Windows 11 Pro**;
- standard edition, **not N**;
- base language **English (United States)**.

The N edition is not selected because removing and later reconstructing media
framework dependencies creates unnecessary product risk around camera,
biometrics and related desktop components without providing a security benefit.

### Deployment locale contract

The installation and normal desktop locale are explicit and must not depend on
Setup/OOBE guesses:

- Windows UI/base language: **English (United States)** (`en-US`);
- primary keyboard/input layout: **US** (`0409:00000409`);
- additional keyboard/input layout: **Russian** (`0419:00000419`);
- **no German keyboard/input profile** (`de-DE` / `00000407`) may be installed by the canonical provisioning path;
- region/home location: **Germany**;
- regional formats for dates, numbers and currency: **German / Germany**;
- time zone: **W. Europe Standard Time**.

The English Windows UI is intentional and independent of German regional
formats. Both US and Russian input layouts must already be present after the
unattended first boot; adding them manually after provisioning is not the
canonical path.

**Product-first configuration boundary (corrected 2026-10-08):** distinguish
*configuration* from *access/transport*. Desired state is expressed in
inspectable Windows Setup answers, supported Windows policy/CSP/ADMX settings,
and supported packaged DSC/WinGet resources, or an off-the-shelf product's
configuration when a Windows-native declarative resource is missing. No custom
resident provisioning logic, package installers, scheduled-task configuration
agents, or perpetual post-logon/post-update scripts that repair keyboard state.

Temporary privilege elevation, authentication, interactive-session creation,
Guest Control and command launch are **access mechanisms**, not alternative
configuration systems. A narrowly scoped bootstrap/UAC/elevated task is allowed
during installation and test iterations to execute the chosen supported
product configuration engine. Prefer arranging a suitable privileged context
using supported Windows Setup provisioning before first logon where possible.
The disposable VM may retain elevated-access tasks, test credentials and
other bench-only plumbing for repeated iterations. **Do not clean the VM merely
to simulate a release.** Production artifacts are built independently with an
explicit file allowlist and fail-closed guard against VM helpers, credentials,
AutoLogon and first-logon commands. Only release-file contents, not the current
VM guest state, define what is shipped. The final production workstation must
have no leftover bootstrap accounts or access mechanisms; that is a separate
machine acceptance condition. The external VM harness may orchestrate access
and verify state, but may not implement a parallel desired-state policy inside
the guest.

Language input profiles are user state, distinct from UserLocale (date/number
formats). Microsoft documents that first-logon region selection may generate
input profiles. Accordingly, testing only the unattended XML is insufficient:
acceptance requires a separate real user-language/input-list read-back after
first logon and after updates. A supported, current-Windows declarative way
to enforce that user list after provisioning is **not yet proven**. Never
silently substitute a PowerShell script, registry deletion or legacy intl.cpl
XML for that missing contract; report the capability gap until a supported
product resource has passed real Windows 11 validation.


License activation is separate from software provenance. A product key may
activate the OS, but activation is not evidence that the installation media is
authentic.

### License procurement is not a security boundary

Retail is preferred when its transferability is worth the price difference;
OEM is acceptable when the savings justify binding the license to this ASUS.
A cheap secondary-market key may be an economic choice with provenance/revocation
risk, but it must never change the software-source rule: the OS image still
comes only from Microsoft. VM-bench activation is not required for configuration
proof.

A second independently installed Windows instance is treated as a separate
licensing question rather than assuming that inability to boot two bare-metal
instances simultaneously grants a second license.

## Installation-media trust

Only an official Microsoft Windows 11 ISO is an accepted OS source.

Current verified bench artifact:

- file: `Windows11_Client_x64_en-us_26300_9457.iso`;
- size: `9047330816` bytes;
- SHA-256:
  `BD4307DF32BC8AF33B39CCECB1174AEB345386630F89A2B86C7A4E36B55EA650`.

The recorded provenance is in
[`vm/ISO_PROVENANCE.md`](vm/ISO_PROVENANCE.md).

Required media workflow:

```text
Microsoft download
        ↓
SHA-256 comparison with Microsoft-published value
        ↓
verified ISO
        ↓
VM install or physical installation media
        ↓
Secure Boot / Trusted Boot runtime chain
```

SHA-256 verification and Secure Boot solve different problems:

- SHA-256 proves the ISO matches the official published image;
- Secure Boot/Trusted Boot protect executable boot/runtime components when the
  machine starts.

Do not download Windows ISO images, installers, "activation helpers", custom
images, driver packs or scripts from license-key resellers.

## Security objective

The core security objective is **compartmentalization**.

The design explicitly rejects this model:

```text
ordinary Windows root/SYSTEM/kernel
        ↓
absolute access to every user secret
```

The desired model is:

```text
hardware / hypervisor security boundaries
        ↓
multiple independent trust domains
        ↓
ordinary Windows VTL0 desktop
```

Compromise of one domain should grant the attacker that domain's authority, not
automatically all user identities and long-lived keys.

Examples of intentionally distinct domains:

- BitLocker + TPM/Pluton boot release;
- Windows Hello keys;
- ESS biometric sensor/matcher path;
- VBS/VTL1 isolated code and data;
- YubiKey recovery key material;
- Ledger transaction-signing keys;
- browser sessions and extension state in ordinary VTL0.

No single software layer is expected to make all other factors irrelevant.

## Threat model

The architecture is designed to preserve useful security properties under
stronger compromise than "one normal user process is malicious".

Relevant attacker classes include:

1. malicious web content or browser extension;
2. malware running as the interactive user;
3. elevated administrator/SYSTEM compromise;
4. arbitrary ordinary Windows kernel/VTL0 compromise;
5. theft of either SSD;
6. replacement or modification of boot artifacts;
7. loss or destruction of the ASUS/TPM;
8. malicious host-side calls into a legitimate enclave API.

The architecture does **not** claim that an already-compromised ordinary OS can
safely display arbitrary transaction context. That is the trusted-context gap
covered later in this document.

The architecture also does not treat firmware/SMM compromise as harmless.
Secure Launch/DRTM reduces the amount of early boot software that must be
trusted for the VBS launch measurement, but hostile platform firmware below or
outside that boundary remains a separate class of risk.

## Trust-domain map

The intended high-level security layout is:

```text
ASUS hardware
│
├── TPM / Microsoft Pluton
│     ├── device-bound key protection
│     ├── BitLocker protector state
│     └── Windows Hello key protection
│
├── IR camera + ESS-capable device path
│     └── biometric input for Windows Hello
│
├── CPU virtualization / hypervisor boundary
│     ├── VTL1 / Secure Kernel / protected services
│     │     └── optional VBS enclave credential broker
│     │
│     └── VTL0
│           ├── Windows kernel
│           ├── SYSTEM/admin services
│           ├── Chrome
│           ├── wallet extensions
│           └── ordinary applications
│
├── YubiKey (offline/recovery domain)
│     └── non-exportable recovery private key
│
└── Ledger (transaction-signing domain)
      └── crypto private keys + trusted device display
```

The exact internal Windows implementation of TPM/Pluton, Hello, VBS and ESS is
owned by the platform. The project configures and verifies those mechanisms; it
does not replace them.

## Physical disk and boot layout

### Two-SSD model

The intended physical layout is:

```text
SSD1
└── existing Windows 11 Home
    ├── its own EFI/boot state
    ├── its own Windows RE state
    └── Device Encryption / BitLocker technology

SSD2
└── Windows 11 Pro security workstation
    ├── GPT
    ├── dedicated EFI System Partition
    ├── Microsoft Reserved partition as required
    ├── BitLocker-protected Windows C:
    └── dedicated Windows RE partition (after C:)
```

SSD2 should receive its own ESP and recovery structures so it can be erased,
reinstalled or removed without creating a boot-repair dependency on SSD1.

**Authoritative firmware boot-selection requirement (2026-10-08):**
The owner chooses the **physical boot disk / RAID logical disk (LUN)** in
the ASUS **firmware boot-device menu**. This is NOT a request for a
two-Windows menu inside Windows Boot Manager, nor for choosing between
two Windows Boot Manager entries in UEFI NVRAM. Each disk must boot its own
Windows using its own ESP and BCD, independently of the presence of the
other disk. The firmware must expose a usable device-selection path for
both SSD1 and the SSD2 RAID LUN. Whether ASUS/RAIDXpert2 firmware exposes
this selection must be verified physically; do not silently substitute
NVRAM-entry selection for disk selection or claim hardware support from VM.
NVRAM entries may exist but cannot be the only means to choose the OS.

Microsoft's BCDBoot /s explicitly writes files and BCD to the nominated
ESP without registering a new Windows Boot Manager NVRAM entry; the
documented default UEFI path is EFI/BOOT/BOOTX64.EFI. Preparing this
fallback path is a candidate to satisfy device-based boot, but real
device-selection behavior remains a separate hardware acceptance gate.

**Target-local boot partitions are a hard acceptance requirement:**

The live two-disk Windows 11 Setup test on 2026-10-08 **FAILED** when the
operator put the protected SSD1 analog Offline, then selected the separate
LUN as Unallocated Space and let stock Windows Setup partition it.
The intended target actually received ONLY an MSR and NTFS partition;
no target-local ESP. Setup failed at Update Boot Code, 0x8007001F, after
successful WIM application. The protected SSD1 VDI GPT/sentinel stayed intact.

Therefore it is false that stock Setup is guaranteed to create an
independent ESP when another GPT disk with an ESP is still enumerated.
**Do not use this unattended+GUI flow on the physical ASUS.**

We still do not require arbitrary project-defined MiB sizes. However,
the install design must use a documented Microsoft path that explicitly
creates/provisions the ESP and BCD on the operator-selected target LUN,
with no disk-index guess and no writes to SSD1. Microsoft documents
WinPE DiskPart UEFI/GPT partition preparation and target-bound BCDBoot
through its /s option; this is the supported next design candidate,
not yet a working accepted full install workflow. BCDBoot /s does not
register a UEFI NVRAM entry and relies on the firmware's standard boot
path. The acceptance target is boot-disk selection, NOT NVRAM-entry
selection.

Audit target-local ESP, MSR, C: and WinRE, independence from SSD1, correct GPT
roles, enabled REAgentC and adequate recovery free capacity. Measure the
effective layout and WinRE location after installation; do not assume recovery
is invariably partition 4 or any particular size.

Windows servicing may resize/recreate WinRE but does not automatically
grow C: when the RAID LUN gains new capacity.

**RAID LUN expansion is a different, explicitly initiated operation.**
RAIDXpert2 first expands the capacity of the independent virtual disk.
The resulting extra space appears AFTER the target recovery partition, so the normal
Windows C: Extend Volume operation is blocked by that intervening partition.
No Windows Update automatically handles that storage expansion. Reuse native,
documented Microsoft recovery and storage operations only when LUN growth is
requested, after an offline recovery/BitLocker state gate:

1. Positively identify the expanded selected RAID LUN and its current
   target-local recovery partition using measured GPT roles and REAgentC.
   Confirm offline recovery and BitLocker readiness; back up WinRE.
2. Disable WinRE with REAgentC and delete **only** the positively verified
   recovery partition (not an assumed fourth partition).
3. Extend C: using supported Windows storage mechanisms while reserving
   adequate current WinRE image space and Microsoft's servicing margin.
4. Recreate an appropriately sized target-local recovery partition after C:,
   set the recovery GPT attributes and register/enable it with REAgentC.
5. Verify actual C: size, EFI/BCD, WinRE, BitLocker protectors/PIN and
   offline recovery. Fail closed if recovery or protection is not working.

This is a documented **rare maintenance transaction**, not a homemade general
partition manager and not a routine step for Windows Update. It must be
tested on a disposable Windows VM, including synthetic virtual-disk expansion
and protection rollback; RAID-controller-specific growth remains the separate
RAIDXpert2 physical experiment. Microsoft's Windows deployment reference
includes a CreateRecoveryPartitions-UEFI example that extends Windows,
shrinks a recovery-sized reserve, and creates the recovery partition. Prefer
adapting that supported flow over inventing a new storage layer.

Microsoft references:
- https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/windows-recovery-environment--windows-re--technical-reference
- https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/oem-deployment-of-windows-desktop-editions-sample-scripts
- https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/configure-uefigpt-based-hard-drive-partitions
- https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/add-update-to-winre

This is primarily an **independence and recovery** property. A separate ESP is
not treated as a confidentiality boundary because a sufficiently privileged
attacker can modify storage that the running OS can access.

### Installation isolation

During physical Windows 11 Pro installation, **SSD1 is placed Offline in
WinPE/Setup before any destructive operation**. Physical removal of SSD1 is not
required. The owner then explicitly chooses the Windows-target RAID virtual
disk in **interactive WinPE DiskPart**. This intentional manual disk-selection step is
not a deviation from the unattended goal: all remaining unattended settings
(edition, locale, OOBE, product configuration) still apply. Do not hardcode
a production DiskID or attempt elaborate NVMe-serial-to-number binding.

The protected SSD1 remains visible for identification but not writable. An
ambiguous disk list, an online SSD1, or a mistaken virtual-disk selection is a
stop condition; the owner must confirm the target before wiping. Isolation is
an additional protection, **not** permission for setup to pick a random disk.

**FAILED mixed Windows Setup installation — STOP gate (2026-10-08):**

The common answer file legitimately requests manual image target selection
using OSImage WillShowUI=Always and no DiskConfiguration or hardcoded DiskID.
That part works. However, on a two-VDI machine, the operator manually
put protected Disk 0 Offline, selected Disk 1 Unallocated Space and clicked
Next. Windows Setup applied the Windows 11 Pro WIM but FAILED to create
a bootable independent target:

- Actual target GPT: MSR (16 MiB) and Windows NTFS only, **no ESP**.
- Panther setuperr.log: BFSVC ServicingBootFiles 0x1F and
  CUpdateBootCode 0x8007001F, during Finalize.
- The protected original VDI's GPT, protective MBR and raw data sentinel
  were subsequently verified unchanged by read-only VDI inspection.
- The absence of an ESP on the selected LUN is unacceptable even if Setup
  were to complete successfully using SSD1's existing ESP.

**The previous 'Offline SSD1 then choose blank LUN in Windows Setup and
let Setup create all partitions' procedure is explicitly rejected.**
On 2026-10-09 that rejected stock Setup path was replaced by operator-controlled
WinPE DiskPart partitioning, DISM image application, target-local BCDBoot /s,
REAgentC registration and the one password-free XML copied to Windows/Panther
for specialize/OOBE. The existing two-disk VM reached a real Windows desktop
once. This is a positive first-boot result, **not** proof of repeat logon,
WinRE Enabled, Windows-side SSD1 Offline, production Secure Boot or ASUS release.
No physical release or installed VM destruction is authorized from a static
XML contract or a first-boot observation alone.

Official Microsoft reference:
https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/automate-windows-setup?view=windows-11
https://learn.microsoft.com/en-us/windows-hardware/customize/desktop/unattend/microsoft-windows-setup-imageinstall-osimage-willshowui
https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/offline-disk
https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/windows-setup-installing-using-the-mbr-or-gpt-partition-style

**Two-disk VM acceptance for this issue:** verify the Windows target's own
ESP/BCD/WinRE and its independent boot, while preserving the protected
Home-like synthetic VDI GPT and sentinel. The synthetic VDI is not a bootable
Windows Home installation; booting actual Home independently is a physical
ASUS gate, not a credible VM simulation.
On physical ASUS, additionally prove selection of SSD1 versus SSD2
RAID LUN as a **boot device** in the firmware boot menu; do not substitute
selection of Windows Boot Manager NVRAM entries. One VDI emulates protected
Home with sentinel data and one VDI emulates the full target RAID LUN. Perform
the real Offline and manual WinPE target-selection steps and also reverse disk
enumeration. Verify sentinel integrity, target-local ESP/WinRE/BCD,
manually created target-local GPT partition roles and working WinRE after Windows Update.
Separately simulate LUN growth and WinRE maintenance. Hardware RAIDXpert2
feasibility is NOT proven by a synthetic VDI.

The original one-disk working VM / installed-clean snapshot is preserved.
Three stock Setup attempts failed; the later manual two-disk deployment reached
the Windows desktop once. Full runtime acceptance, a second cold boot and
reverse-enumeration tests remain UNPROVEN. A running-VDI host read-back is
provisional; BitLocker now prevents unauthenticated offline inspection of C:.

### Storage-allocation layer status

The long-term allocation requirement is to avoid repeated shrink/move cycles
between several OS installations on the 4 TB SSD. True shared thin provisioning
would be ideal, but the ordered **Lexar NM790 4 TB
(LNM790X004T-RNNNG)** does not expose NVMe Namespace
Management/Attachment and therefore cannot supply hardware thin namespaces.

**RAIDXpert2 is selected as the intended allocation layer**, not a throughput
RAID requirement. Hardware feasibility and supported driver/firmware operation
on the ASUS are tested in a **separate storage experiment**, outside the scope
of the Windows installation-configuration issue. The accepted logical model is:

```text
SSD1
└── existing Windows 11 Home, preserved independently if the AMD RAID mode
    can expose it as a legacy/non-member disk

SSD2 / Lexar NM790 4 TB
├── small bootable virtual disk → security Windows
├── small bootable virtual disk → optional dev Windows
├── small bootable virtual disk → optional Linux
└── unused capacity for later Online Capacity Expansion
```

This is deliberately not described as thin provisioning: an allocated virtual
disk owns its assigned capacity, deleted files do not donate that capacity to
another virtual disk, and shrink is not assumed. The useful property under
evaluation is **small initial allocation plus Online Capacity Expansion in
small increments** without moving neighbouring GPT partitions.

The architecture must not span SSD1 and SSD2 with RAID0 or another
failure-coupled aggregate merely to obtain one large device. Existing Home
recoverability and failure independence are more valuable than striping
performance.

The following are acceptance criteria of the **separate RAIDXpert2 hardware
experiment**, not blockers to completion of this Windows Setup configuration
issue. Before any physical deployment depends on RAID, that experiment must
prove on the exact FA401EA path that:

- firmware exposes the required NVMe RAID mode;
- SSD1 can remain legacy/non-member without destructive initialization;
- the existing Home installation can be prepared to boot through the AMD RAID
  boot-critical driver stack;
- single-disk virtual disks on NM790 can coexist and be expanded independently
  from still-unused capacity;
- expansion preserves bootability and BitLocker state;
- a failed ASUS does not make the data practically unrecoverable: supported
  migration and an independently tested raw-disk recovery path must exist.

The Windows Setup VM bench models the RAID virtual disk with a normal VDI;
it does not need the AMD controller to validate disk selection or GPT layout.
The RAID experiment independently establishes the supported hardware layer.
The Setup answer and checks must not rely on guessed RAIDXpert2 device IDs.

### No cross-OS auto-unlock

Booting one Windows installation must not automatically unlock the other OS
volume.

Do not configure BitLocker auto-unlock between the Home and Pro OS volumes.

A TPM does not make every encrypted OS volume automatically available merely
because the same physical TPM is present. Each OS volume follows its own
protector/boot policy.

If the Home SSD is intentionally left unencrypted, a Pro administrator could
read its NTFS contents; therefore Home encryption should remain enabled when
that SSD contains data whose at-rest confidentiality matters.

## Normal boot path

The production boot path is conceptually:

```text
UEFI firmware
        ↓
Secure Boot
        ↓
Windows Boot Manager / trusted boot chain
        ↓
BitLocker TPM policy + startup PIN
        ↓
OS volume release
        ↓
Windows hypervisor / VBS launch
        ↓
Secure Kernel / VTL1
        ↓
ordinary Windows VTL0
        ↓
Windows Hello / ESS for in-OS identity
        ↓
sensitive workload
```

The exact ordering of internal measured-boot and hypervisor initialization is
owned by Windows; this diagram expresses trust boundaries and user workflow,
not an implementation-level boot trace.

## BitLocker

### Production protector

The Windows 11 Pro OS volume uses:

```text
TPM + startup PIN
```

for the normal preboot path.

The startup PIN is an **early-boot credential**, entered before ordinary
Windows applications are running. It is not reused as a routine application or
desktop authentication secret.

TPM anti-hammering and BitLocker policy provide a materially different security
model from storing a short reusable PIN as a normal password hash.

### Recovery

Maintain a BitLocker recovery key offline, outside the laptop.

The recovery key is exceptional recovery material, not a normal daily
credential.

An unexpected BitLocker recovery event is a security signal, not merely an
annoying password prompt. If there is no understood benign cause, the preferred
response is to stop, use trusted recovery/install media, investigate/rebuild,
and avoid feeding recovery material into an environment whose boot integrity is
in doubt.

Recovery material must not be emitted into automated logs, Git, issue comments
or VM run artifacts.

### Separate Hello PIN

The Windows Hello PIN remains available as fallback when biometric login is
unavailable.

The Hello PIN is device/TPM-bound authorization, not an ordinary reusable
password hash. However, its digits are still entered through the running OS,
so the architecture does not claim that PIN entry is invisible to an already
hostile VTL0 kernel. This is another reason ESS Face is the preferred normal
in-OS path.

For compartmentalization, it should be **distinct from the BitLocker startup
PIN**. Reusing the preboot PIN in normal userspace would unnecessarily expose
the same secret to a larger attack surface.

Normal daily intent is therefore:

```text
boot: BitLocker startup PIN
desktop/app authorization: ESS Face
fallback only: distinct Hello PIN
```

This accepts two memorized PINs in exchange for keeping the high-value preboot
secret out of normal userspace. The Hello PIN should be needed rarely if ESS
Face works reliably.

## TPM and Microsoft Pluton

Pluton/TPM is a hardware root for device-bound keys, measured policy and
hardware-protected key operations.

The architecture uses it for platform functions such as:

- BitLocker protector policy;
- Windows Hello keys;
- device-bound key protection and attestation where the platform uses it.

Pluton is not treated as a replacement for VBS. They solve different problems:

- TPM/Pluton protects device-bound key material and key operations;
- VBS creates isolated execution/memory domains that remain meaningful even
  when ordinary VTL0 is compromised.

The design should prefer supported Windows abstraction layers over
project-specific direct TPM plumbing unless a concrete platform gap requires
otherwise.

## Virtualization-Based Security

### VTL0 is not the final trust boundary

Ordinary Windows kernel, drivers, SYSTEM services and applications run in the
normal world, conceptually VTL0.

VBS uses the Windows hypervisor to create a stronger isolation boundary for
VTL1/Secure Kernel/protected services.

The architecture relies on the property that arbitrary VTL0 kernel compromise
does not automatically imply direct read/write access to private VTL1 memory.

That does **not** mean a compromised VTL0 is powerless. It can still:

- control ordinary UI;
- invoke exposed enclave entrypoints;
- manipulate browser state;
- perform denial of service;
- attempt confused-deputy attacks;
- steal plaintext that an application legitimately receives in VTL0.

This distinction between **memory confidentiality** and **authorized-oracle
abuse** is fundamental to the vault design.

## HVCI / Memory Integrity

Hypervisor-protected Code Integrity / Memory Integrity is part of the production
baseline.

Its purpose is to move Code Integrity enforcement into the VBS-protected
security architecture and reduce the ordinary kernel attack surface, including
known vulnerable-driver paths and writable/executable kernel memory abuse.

It is a hardening layer, not a substitute for the stronger secret boundaries
provided by TPM/Pluton, ESS, VBS enclaves, YubiKey or Ledger.

### Production UEFI Lock (physical ASUS finalization)

Owner is physically present at the ASUS and accepts firmware-presence recovery;
there is **no portability reason** to omit UEFI Lock. The workstation must
converge to VBS and HVCI with their UEFI locks enabled. Apply the reviewed
native DSC overlay `windows/configuration/security-hardware.winget` only **after**
VBS/HVCI are proven running on the physical ASUS, hardware drivers are accepted,
and WinRE/recovery access is established. It sets both DeviceGuard and HVCI
`Locked=1`. Production acceptance must verify effective runtime and locked
state across a reboot; registry value alone is not proof of firmware enrollment.

The shared VM/physical baseline deliberately **does not manage** either
`DeviceGuard/Locked` or `HVCI/Locked` value. The physical ASUS-only overlay
exclusively sets both to `1` after verified VBS/HVCI runtime and recovery.
Reapplying the common workstation baseline must never undo or request a
reversal of firmware locks. On the NEM-backed bench VTL1 runtime is not
provable; the hardware overlay is excluded.

The real recovery cost of UEFI Lock is not portability: when HVCI causes a
boot-time failure, disabling the lock may require entering the local UEFI setup,
turning Secure Boot off temporarily and following Microsoft's WinRE recovery
procedure. Do **not** set VBS `Mandatory=1`: unlike UEFI Lock it makes the OS
refuse to boot when virtualization components fail. Recovery is a product gate.

Source: https://learn.microsoft.com/en-us/windows/security/hardware-security/enable-virtualization-based-protection-of-code-integrity

## Secure Launch / DRTM

Enable and verify **System Guard Secure Launch / DRTM** on the physical ASUS
when supported by the final firmware/build configuration.

The useful property is concrete:

- ordinary UEFI firmware executes first;
- a dynamic root-of-trust launch resets/re-establishes the dynamic measurement
  chain for the protected Windows hypervisor/Secure Kernel launch;
- the VBS launch therefore does not need to trust the entire enormous early
  firmware execution history in the same way a purely static measurement chain
  would.

Secure Launch does not make compromised SMM/firmware harmless. It narrows the
trusted launch boundary; it does not eliminate platform-firmware risk.

VirtualBox evidence is not accepted as proof of real ASUS DRTM behavior.

## Windows Hello and Enhanced Sign-in Security

### Normal identity path

Windows Hello is the primary in-OS user-verification mechanism.

Normal user-verification preference:

```text
ESS Face
  ↓
Windows Hello
  ↓
hardware-backed user authorization
```

The Hello PIN is fallback, not the preferred routine prompt.

**Final interactive-account credential contract:** the owner separately sets
and retains a **long, high-entropy emergency/recovery account password**
during a trusted owner-controlled enrollment step. It is not generated by the
VM bench, included in unattended installation media, or used for everyday
sign-in. Normal sign-in/reauthorization uses Windows Hello Face via the built-in
IR camera (ESS where supported); the separate Hello PIN is the fallback.
This long account password is **not** the BitLocker recovery key or startup PIN:
those protect different boundaries. Any install-time bootstrap account is
transient access plumbing and may not become the owner's final identity.

### ESS is already evidenced on this ASUS

ESS support on the target is not merely inferred from "IR camera" marketing.

The existing Windows 11 Home installation has produced Windows Biometrics
Operational event 1108 messages showing:

- the facial-recognition software device isolated in a
  **Virtual Secure Mode** process;
- the Windows Hello Face bootstrap/virtual software path as expected.

A capability check also showed the built-in ASUS IR/FHD camera and the relevant
USB host-controller path advertising the secure-device capability.

The event stream also contains a Windows Hello Face virtual/bootstrap software
device running in Local System. That does not negate the ESS result: the
security-relevant facial-recognition path is the separate device explicitly
reported as isolated in a **Virtual Secure Mode** process.

Therefore the production architecture treats **ESS Face on the built-in camera
as an already demonstrated machine capability**, to be re-verified after the
Windows 11 Pro installation.

External cameras are not assumed to provide the same ESS path.

### What Hello proves and what it does not

Windows Hello/ESS provides strong user presence/identity verification and
hardware-backed key authorization.

It does **not** by itself prove that the user knowingly approved an arbitrary
application-specific semantic such as:

```text
"release the Binance password"
```

rather than:

```text
"release the Amazon password"
```

The architecture therefore distinguishes:

- **identity/presence** — what Hello/ESS is good at;
- **trusted transaction context** — a separate problem.

Do not claim that a caller-supplied string in a normal Hello/consent UI is
cryptographically bound to a VBS-enclave request unless the platform API
explicitly provides and documents that binding.

## Administrator Protection

Use **Windows Administrator Protection** when available and supported on the
installed Windows 11 Pro build.

The intended model is a deprivileged normal session with just-in-time elevation
for administrative operations, with Windows Hello used for the elevation
authorization path.

Administrator Protection is architecturally preferable to treating a
permanently elevated administrator token as the normal desktop identity.

Important boundary statements:

- classic UAC/Secure Desktop protects against ordinary user-mode UI spoofing,
  but it is not a security boundary against an already-hostile kernel;
- Administrator Protection is a distinct modern mechanism;
- do **not** describe Administrator Protection itself as "running in VBS"
  unless Microsoft explicitly documents that implementation;
- the design may benefit from VBS/ESS overall without conflating those
  mechanisms.

## Credential Guard

Credential Guard is **not a production requirement** for this standalone
workstation.

Its main value is protecting domain authentication material such as Kerberos
and NTLM secrets. That is not the dominant secret class for this standalone
crypto/cloud workstation.

Do not buy a higher Windows edition or redesign the machine merely to obtain
Credential Guard.

If it is available under the final supported configuration at zero meaningful
cost, enabling it may be considered separately, but it is not part of the core
acceptance gate.

## App Control / WDAC

Application Control can reduce executable and driver attack surface and may be
useful later.

It is not the primary solution for the browser-extension threat:

- an allowed Chrome process can still execute a malicious allowed/installed
  extension;
- a malicious extension update remains a supply-chain problem inside the
  allowed browser.

The initial architecture therefore prefers:

- a dedicated sensitive Chrome profile;
- a small manual allowlist of required wallet extensions;
- no unnecessary extensions;
- normal browser/vendor update channels;
- Ledger verification for irreversible crypto actions.

Do not introduce a heavy corporate App Control management stack unless its
marginal security value justifies the operational cost.

## Windows Sandbox

Windows Sandbox may be used for opening unknown/untrusted files when useful.

The default `sandbox-untrusted.wsb` remains **offline**: a deliberately
selected host inbox is exposed read-only, with clipboard/network/device
redirection disabled. This is a convenient exploratory desktop, **not** a
network-behavior monitor or credential root of trust.

The user also requires convenient *observation of suspicious behavior*:
`process.exe attempted destination example.com:443`, then blocked, with
process identity, time, target and an accessible event history. Windows Sandbox
has no built-in per-domain allow/deny dialog or reliable outbound-event
history. Disabling networking removes the sandbox virtual NIC, so network
tools may not observe DNS names/remote connections at all. Do not claim the
offline Sandbox can disclose every attempted network destination.

A distinct `sandbox-networked.wsb` explicitly enables the Hyper-V default
switch and starts the built-in `resmon.exe` Resource Monitor as a lightweight,
convenient GUI for per-process TCP and traffic inspection. It preserves the
same read-only single-folder mapping, Protected Client and blocked host device
redirection as the offline profile.

**Required change before accepting networked use on the ASUS:** egress must
be **internet-only**, not Hyper-V Default Switch's unrestricted LAN+internet.
At the host-side enforcement layer deny guest access to Windows host addresses,
all directly connected LAN/VPN prefixes, RFC1918, loopback, link-local, CGNAT,
IPv6 ULA/link-local and other non-public destinations. Ensure a working DNS
path that does not reopen access to host/private services. Allow external
public addresses, subject to ordinary malware exfiltration risk.

Prefer first-party Windows **Hyper-V Firewall** (per-`VMCreatorId` and
`RemoteAddresses` on Windows 11), if native Windows Sandbox actually exposes
a distinct, stable creator identity and effective packet filtering. This must
be discovered and verified on the physical ASUS; never guess or reuse the WSL
creator GUID. Test host LAN/VPN deny, host-access deny, IPv4/IPv6 bypass deny,
public HTTPS success and persistence across Sandbox restarts. The native
`.wsb` does not configure these rules and no such live proof exists yet.
If Windows Sandbox cannot be isolated separately, use a dedicated Hyper-V VM
with its own network policy rather than globally blocking ASUS/WSL traffic.

**Until that proof, `sandbox-networked.wsb` is a prepared, UNRESTRICTED
connectivity diagnostic, not an internet-only security profile,** and should
not be used for executing adversarial programs or advertised as safe.

For dynamic malware/network research, design a **separately isolated analysis
VM**, with a network policy enforcement point and logs outside the untrusted
guest, preventing real LAN access or internet exfiltration. Prefer existing
products (e.g. Safing Portmaster domain-aware monitoring and prompt/deny UI,
Sysinternals Procmon for process/file/registry behavior) over any homemade
monitor. An in-guest firewall alone is not trustworthy against guest admin-level
malware; experiments must never expose the hardware wallet/credential host to
the suspicious guest. This is a distinct staged product, not a promise that
WSB can behave like a professional malware sandbox.

Windows Sandbox is not a substitute for VBS-enclave, YubiKey or Ledger
boundaries.

## Credential strategy

### Prefer non-password credentials where services support them

Passkeys/WebAuthn/client-key authentication are preferable to passwords because
a private key can remain hardware/device bound and need not be exposed as a
reusable plaintext credential.

Windows Hello is therefore preferred for passkey-style user authentication
where the service supports it.

A password is fundamentally weaker at the moment of use: to fill a password
into Chrome, plaintext eventually exists in ordinary VTL0/browser memory.

The architecture does not pretend otherwise.

### Browser password reauthentication

Chrome's supported "use Windows Hello when filling passwords" behavior is
useful at the ordinary-user/same-session layer and matches the desired UX of
fresh user presence before credential use.

It is not, by itself, the final defense against an already-hostile VTL0 kernel.

The stronger long-lived-secret objective is handled by the VBS credential
broker design below.

## VBS credential broker / vault

### Scope

Do **not** build a complete password manager.

Do not build:

- a new sync service;
- a new browser UI ecosystem;
- a new general password database format unless unavoidable;
- custom cryptographic primitives;
- a general desktop secret-service replacement.

Build, if the proof validates the economics, only a **small VBS-enclave
credential broker/policy component** that addresses the specific platform gap:
protecting the master credential secret and preventing silent bulk export from
VTL0.

### Security objective

The target split is:

```text
VTL1 / VBS enclave
    ├── vault master K
    ├── record decryption
    ├── authorization policy
    ├── sealing / identity checks
    └── recovery-key unwrap path

VTL0 host
    ├── UI
    ├── browser integration
    ├── encrypted vault blob
    └── untrusted transport
```

The host may be malicious.

The security claim is **not** "malicious VTL0 cannot call the enclave".

The claim is:

- malicious VTL0 cannot directly read enclave memory or export K;
- there is no bulk plaintext-dump API;
- the enclave exposes only narrow, policy-checked operations;
- each credential release is deliberate at the enclave API level;
- long-lived master material remains outside VTL0.

### Master key

Generate a random **256-bit master key K** using the supported system CSPRNG in
the trusted implementation path.

Do not derive K from:

- the BitLocker startup PIN;
- the Hello PIN;
- a user password;
- MAC addresses, clocks or other hand-mixed local entropy.

No "move the mouse for entropy" ceremony is required for a normal system CSPRNG
after initialization.

### Normal user-bound protection

The daily path should use the supported Windows Hello / VBS user-bound
mechanism rather than inventing a second owner-managed TPM wrapper.

Conceptually:

```text
Windows Hello / user-bound authorization
        ↓
VBS enclave can use/unseal K
        ↓
one-record operation
```

The implementation must not reduce this to:

```text
untrusted host says hello_ok=true
```

A host-provided boolean is not a security boundary.

Use the supported VBS-enclave/Windows-Hello user-bound pattern or equivalent
documented mechanism so that the authorization decision is not merely trusted
because VTL0 claimed it succeeded.

### Narrow API

There must be no:

```text
ExportKey()
DumpVault()
GetAllPlaintext()
```

baseline entrypoint.

The minimal public surface should look conceptually like:

```text
ReleaseCredential(record_id, fresh_authorization)
UpdateCredential(record_id, encrypted_input, authorization)
RecoverVault(recovery_authorization)
```

Only operations actually needed by the product should exist.

Metadata may remain outside the enclave if disclosure of that metadata is
acceptable. Secret values and K do not.

### Host compromise and oracle abuse

A malicious VTL0 host can:

- call legitimate enclave entrypoints;
- lie in its own UI;
- request a different record than the user intended;
- replay allowed requests unless nonce/state policy prevents it;
- instantiate another host process around the same enclave code;
- deny service.

Therefore enclave security must not depend on:

- host process identity;
- "SYSTEM only" checks;
- a particular PID;
- UI text drawn by the host.

This is why enclave identity, request binding and anti-replay state matter.

### Enclave identity and sealing

Use restrictive enclave identity/sealing policy.

The design must explicitly decide and document use of the supported identity
policy dimensions rather than accepting a permissive "anything signed by us
forever" rule. Relevant policy classes include concepts such as
`EXACT_CODE`, `SAME_PRIMARY_CODE`, `SAME_IMAGE`, `SAME_FAMILY` and
`SAME_AUTHOR`; the most permissive policy is not the default choice merely
because upgrades become easier.

Versioning must include an anti-rollback story.

A hostile host must not be able to restore an old vulnerable enclave + old
sealed state and silently regain a previously removed capability.

The exact supported VBS enclave identity policy is an implementation decision,
but it must be reviewed before production.

The implementation should start from Microsoft's supported VBS-enclave tooling
and user-bound/Windows-Hello examples (including the HostAppUserBound pattern)
rather than inventing the host/enclave authorization handshake from scratch.
Production enclave binaries must also follow the platform's enclave integrity,
CFG and signing requirements; debug/test signing is not a production trust
model.

### Plaintext-at-use limitation

When a password is legitimately released to Chrome, that specific plaintext
password exists in VTL0.

Therefore a hostile Windows kernel can potentially steal **that credential at
the moment it is used**.

The VBS-vault objective is narrower and still valuable:

```text
hostile VTL0
    ≠ automatic master-key theft
    ≠ automatic bulk vault dump
    ≠ automatic access to every never-used credential
```

This is why passkeys/hardware-bound keys remain preferable whenever available.

## Trusted-context gap

### The remaining problem

Suppose the user is present and ESS verifies them.

A malicious VTL0 host could still attempt:

```text
enclave request: release Binance
host UI:          "Authenticate for Amazon"
user:             Face verified
```

If the authorization result is not cryptographically bound to the enclave's
exact `record_id`, presence alone does not prove transaction intent.

A generic third-party VBS enclave cannot simply draw arbitrary pixels through a
trusted VTL1 display path. Its restricted runtime is not a normal desktop
process: it does not get ordinary user32/GDI/DWM UI or direct arbitrary device
I/O. Any screen/device interaction normally has to be mediated by the untrusted
host side.

Secure Desktop is not considered sufficient against hostile VTL0 kernel code.

### Version 1 accepted compromise

The initial production architecture may proceed without a generic trusted
display.

Version 1 therefore accepts a residual **confused-deputy/oracle** risk while
the user is actively present.

This is acceptable only if the stronger properties remain true:

- K stays out of VTL0;
- bulk export is impossible through the normal API;
- credential release requires fresh user verification;
- release is one-record-at-a-time;
- rate/replay/state controls are explicit;
- the residual risk is documented rather than disguised as solved.

Trusted display is a hardening phase, not a blocker for the first useful
system.

## Phase 2 external trusted display

Research a small external device acting as a trusted semantic display and
physical confirmation channel.

Conceptual device:

```text
MCU
+ small display
+ physical button
+ device key
+ USB/serial transport
```

The USB/serial transport may be fully hostile.

Security comes from authenticated content, not trusted transport.

### Candidate protocol

1. external display generates a fresh nonce;
2. untrusted VTL0 transports the nonce to the enclave;
3. enclave constructs a request such as:

```text
{
  op: "release",
  record: "binance.com",
  nonce: <display nonce>,
  request_id: <fresh id>
}
```

4. enclave authenticates/signs the request;
5. VTL0 transports it to the display;
6. display verifies the enclave/broker identity and signature;
7. display shows the authenticated record/action;
8. user presses the physical button;
9. display produces an authenticated ACK bound to the same
   `nonce + record + request_id`;
10. enclave verifies the ACK before releasing the credential.

If VTL0 changes `binance.com` to `amazon.com`, signature verification fails.

If VTL0 replays an old confirmation, nonce/request binding fails.

If VTL0 drops or delays traffic, the result is denial of service, not silent
semantic substitution.

### Key establishment

The phase-2 design must include a real provisioning story for mutual identity:

- how the display knows the legitimate enclave/broker public identity;
- how the enclave knows the legitimate display identity if ACKs are signed;
- how replacement/recovery works;
- how old devices/keys are revoked.

Do not treat "USB device connected" as identity.

## YubiKey recovery architecture

A YubiKey-class token is the preferred independent recovery factor for the new
Windows design.

The existing Rutoken is **not** a production dependency for this architecture.
It may remain useful for unrelated existing signing keys, but the Windows
workstation should not contort itself around it. Existing Rutoken signing/key
containers are not to be modified, migrated or repurposed merely to satisfy
this workstation design.

### Daily use

YubiKey is **not required for normal daily login or credential release**.

Normal path remains:

```text
BitLocker startup PIN
→ Windows
→ ESS Face / Windows Hello
→ normal application authorization
```

If the camera fails, Hello PIN is the built-in fallback.

There is no v1 requirement to implement a custom Windows Credential Provider or
make YubiKey a mandatory local-login mechanism. Native Windows FIDO2/security-
key sign-in is not assumed to be a standalone local-account replacement; if a
future requirement wants token-based local login, Yubico's supported login
product or another documented path must be evaluated separately instead of
pretending the Settings "Security key" page automatically solves local login.

### Vault recovery

The vault must have a recovery path independent of the ASUS TPM/Pluton.

Candidate design:

```text
vault master K
├── normal user-bound VBS/Hello protection on ASUS
└── recovery wrapper encrypted to YubiKey-held asymmetric key
```

The YubiKey private key must be generated/held as non-exportable token key
material.

Recovery then requires possession of the YubiKey plus its local authorization
(PIN/touch as appropriate to the selected application/protocol).

The exact YubiKey model and interface (for example PIV for asymmetric
unwrap/decrypt/sign capability, FIDO2 for service authentication) are selected
after the base Windows and vault PoC are proven.

Do not assume FIDO2 by itself is an arbitrary general-purpose decryption API.

The recovery token should normally be stored separately from the laptop.

## Ledger / wallet architecture

Ledger is an independent transaction-signing trust domain.

For Ledger-backed accounts:

- the seed/private key remains on Ledger;
- MetaMask/Phantom/other wallet extensions are interfaces, not key custody;
- do not import the real Ledger seed into a browser/software wallet;
- do not import a software-wallet seed into Ledger merely to make the accounts
  look equivalent;
- verify recipient, amount and action on the Ledger display;
- keep blind signing disabled by default;
- enable blind signing only for a specific protocol when strictly required and
  with explicit understanding of the lost display assurance.

A compromised browser/extension/Windows VTL0 may:

- alter dApp UI;
- substitute destination data before signing;
- manipulate session state;
- attempt malicious transaction payloads.

It still should not be able to extract the Ledger private key.

For irreversible crypto actions, the Ledger display is the trusted semantic
confirmation path available today.

## Browser model

Chrome is the required browser for the sensitive crypto/wallet workload.

Use a dedicated sensitive Chrome profile with:

- only required wallet/crypto extensions;
- no extension sync with unrelated profiles;
- minimal general web browsing;
- official Google update channel;
- Windows Hello reauthentication where supported and useful.

Ordinary browsing should use a separate browser/profile so arbitrary browsing
state, cookies, downloads and extensions do not accumulate in the sensitive
profile. The exact general-purpose browser is not an architecture constraint;
the Windows baseline uses **Microsoft Edge** for this role because it is
Microsoft-maintained, already native to Windows, and avoids adding another
third-party browser/update channel. Chrome remains reserved for the dedicated
sensitive profile.

The user may serve as the wallet-extension allowlist. A large enterprise browser
policy framework is not required merely to encode the same tiny list unless
automation later provides a clear lifecycle advantage.

## Software provenance and channels

Security-critical executable software should come from authoritative vendor
channels:

- Windows / Windows Update: Microsoft;
- Chrome: Google;
- ASUS device/firmware software: Microsoft Update and/or ASUS-supported
  channels as justified;
- YubiKey software/firmware/tools: Yubico;
- Ledger firmware/software: Ledger-supported channel;
- wallet extensions: official extension-store publisher identities and project
  provenance.

Do not install alternate "driver updater", "security optimizer", activation or
download-wrapper utilities.

## Update and maintenance model

### Supported vendor updaters, not a custom package manager

Windows owns OS/security maintenance.

Chrome owns Chrome update delivery through its supported vendor channel.

Defender/signature/platform updates remain on supported Microsoft mechanisms.

The project may add **policy glue and audit**, but it must not build a parallel
package-management ecosystem.

### Sensitive-work gate

Sensitive work must not begin while the machine is knowingly outside required
security maintenance policy.

The desired startup/session policy is:

```text
boot
  ↓
network available
  ↓
check required security/update state
  ↓
pending required update/reboot?
  ├── yes → apply/complete update and reboot if required
  └── no
  ↓
verify security posture
  ↓
release sensitive workload
```

The user should receive a clear state such as:

- current / safe to proceed;
- updated successfully / reboot required or completed;
- update/security gate failed.

Recovery/admin access does not need to be blocked merely because sensitive
work is gated.

Do not turn this policy glue into a replacement for Windows Update.

### Reboots

A real Windows reboot is acceptable and expected after security/platform
updates.

Unlike the old portable Linux design, there is no requirement to preserve an
external one-time firmware boot selection across restart.

## Defender and firewall

Windows Defender and Windows Firewall remain enabled as platform baseline
protections unless a concrete supported replacement is selected.

Do not weaken these controls merely to make wallet/browser tooling easier.

Any exception must be narrow, documented and tied to a demonstrated workload
requirement.

## Recovery and rebuild

The Windows OS is considered **disposable system state**.

If the system becomes untrusted or badly damaged, the preferred security
recovery is often:

```text
power off
↓
boot trusted Microsoft installation/recovery media
↓
wipe/reinstall Windows 11 Pro on SSD2
↓
fully update / restore supported configuration
↓
re-establish Windows Hello / ESS
↓
restore cloud/app state
↓
recover vault using independent recovery factor if TPM-bound state is gone
↓
resume sensitive work only after audit passes
```

There is no requirement to preserve a compromised Windows system instance.

The design favors clean supported rebuild over elaborate attempts to salvage a
security-compromised OS.

### Recovery material

Keep offline, outside normal machine state:

- BitLocker recovery key;
- vault/YubiKey recovery factor;
- any service-level recovery codes that are required;
- installation-media provenance/checksums as practical.

Recovery material must not all live in the same stolen laptop bag if avoidable.

## Existing Windows Home installation

The existing Windows 11 Home installation on SSD1 remains outside the security
workstation's normal runtime.

Requirements:

- preserve its ability to boot/recover independently;
- keep its own volume encryption enabled if its data matters;
- do not configure automatic unlock from the Pro environment;
- do not place required Pro boot/recovery state on SSD1;
- do not make SSD1 presence a prerequisite for Pro boot.

The Home installation is not considered a trusted recovery environment for the
Pro security workstation merely because it is on the same laptop.

Trusted recovery starts from known-good recovery/installation media.

## Provisioning architecture

### Canonical unattended mechanism

The canonical installation contract is a repository-owned Windows-native
**`Autounattend.xml`** consumed by Windows Setup. The same answer file and the
same Windows Setup semantics must be usable in:

- the VirtualBox bench from attached answer/configuration media; and
- production installation from trusted USB/media on the ASUS.

VirtualBox-specific `IUnattended` is not the production deployment mechanism
and must not be the basis of acceptance. It may be used only for diagnostic
experiments that do not define the final install path.

The answer file must explicitly select **Windows 11 Pro, non-N**, apply the
deployment locale contract above, and complete supported Windows Setup/OOBE
without manual *installation troubleshooting*. The VM may reach
its disposable test desktop. Production **must not auto-logon**: after Setup,
owner enrollment and deliberate interactive sign-in are required. The owner
sets a separate long recovery account password and configures Windows Hello
Face/ESS on the physical ASUS; those user actions are not Setup defects.

"Same answer file" means a **single renderer with identical setup
semantics**. Only per-install bootstrap identity fields (username,
password, display name and hostname) are bound when producing media.
No VM-only AutoLogon or Guest Additions commands are allowed in the answer.
VirtualBox Guest Additions and remote access must be established outside
the XML by supported bench plumbing. Existing working VM has them; the
new-install access bootstrap is not yet accepted.

### Exhaustive install-time contract

Before another unattended-install attempt, the renderer and its static
contract test must prove the following values are present exactly:

| Area | Required effective value | Windows mechanism / proof |
|---|---|---|
| OS source | official Microsoft ISO only | SHA-256 must equal the value in `vm/ISO_PROVENANCE.md` before rendering or boot |
| Edition | Windows 11 Pro, non-N | `ImageInstall/OSImage/InstallFrom/MetaData` with `/IMAGE/NAME = Windows 11 Pro`; final audit rejects Pro N |
| Setup UI | English (United States) | `Microsoft-Windows-International-Core-WinPE/SetupUILanguage/UILanguage = en-US` |
| Installed UI | English (United States) | `UILanguage = en-US` in `windowsPE` and `oobeSystem` |
| Non-Unicode system locale | English (United States) | `SystemLocale = en-US` |
| Regional formats | German / Germany | `UserLocale = de-DE` in `windowsPE` and `oobeSystem` |
| Default keyboard | US | first `InputLocale` entry exactly `0409:00000409` |
| Additional keyboard | Russian | second `InputLocale` entry exactly `0419:00000419` |
| Forbidden keyboard | no German layout | no `0407:00000407`, no German input profile anywhere in the product render; runtime audit treats either as FAIL |
| Home location | Germany, GeoID 94 | effective state must audit as GeoID 94; because International-Core Unattend does not expose a HomeLocation/GeoID setting, converge it through the supported International configuration path if Setup does not derive it |
| Time zone | W. Europe Standard Time | `TimeZone` in `specialize` and `oobeSystem`; runtime audit must match exactly |
| Computer name | explicit, environment-bound | no random Setup-generated product hostname; bench may use `WINBENCH` |
| EULA | accepted by unattended setup | `UserData/AcceptEula = true` |
| Setup edition key | public Microsoft Windows 11 Pro GVLK only | `UserData/ProductKey/Key = W269N-WFGWX-YVC9B-4J6C9-T83GX` with `WillShowUI = Never`; this is a public Setup selector, not the user's activation credential and no `Microsoft-Windows-Shell-Setup/ProductKey` is set |
| Microsoft Account | not required for provisioning | `OOBE/HideOnlineAccountScreens = true` plus a local bootstrap account |
| Network page | no OOBE network dependency | `OOBE/HideWirelessSetupInOOBE = true`; trusted installation must be able to start offline |
| OOBE defaults | no interactive Express-settings page | `OOBE/ProtectYourPC = 3` |
| Unsupported OOBE bypasses | forbidden | no `SkipMachineOOBE`, no `SkipUserOOBE`, no registry/BYPASSNRO trick |
| Destructive disk | only owner-selected RAID virtual disk | interactive target selection after SSD1 Offline; no unattended wipe against a guessed or hardcoded DiskID; prove the manual Setup/WinPE sequence |
| Non-target SSD1 | preserved/offline during destructive Setup | bare-metal pre-Setup gate; installation must abort rather than guess if this cannot be established |
| Partition table | GPT/UEFI target-local layout | selected RAID virtual disk receives dedicated ESP + MSR + Windows C: + WinRE, in Microsoft's recommended order |
| ESP | dedicated target-local FAT32 ESP | operator-verified WinPE DiskPart `create partition efi size=300`, formatted FAT32 |
| MSR | dedicated target-local MSR | operator-verified WinPE DiskPart 16 MiB partition |
| Windows volume | target-local OS partition | NTFS C: on the operator-selected LUN, sized by stock Setup; never `InstallToAvailablePartition=true` |
| WinRE | target-local recovery after Windows C: | operator-created 2048 MiB recovery partition, registered with REAgentC; verify actual `winre.wim`, free capacity and Enabled state after boot |
| Cross-OS dependency | none | no boot/recovery structure for Pro may be placed on SSD1; no OS-volume auto-unlock is configured |
| Account secret | no final production secret in media/repo/logs | any unattended bootstrap credential is per-install ephemeral infrastructure, never a final user credential, and must be removed/rotated before production acceptance |
| Setup/owner sign-in boundary | no manual Setup troubleshooting; no production AutoLogon | answer suppresses the language-selection page; VM can enter its test desktop, production requires intentional sign-in and separate owner-secret/Hello enrollment |
| Post-install boundary | separate from Setup | PowerShell/WinGet/DSC, updates, Chrome, BitLocker, Hello/ESS, VBS/HVCI and workload software are not falsely claimed as `Autounattend.xml` work |

A visible language-selection page is therefore an immediate **FAIL**: Microsoft
documents that when an implicitly discovered `Autounattend.xml` is in use,
that page is not displayed. The bench must stop rather than click through it.

The canonical product file remains `Autounattend.xml` at the root of
removable installation/configuration media. Production installation on the ASUS
places that file at the root of the trusted physical USB installation media.
**The owner creates the bootable Microsoft USB themselves**; neither an ISO
writer nor a USB image builder is a requirement of this project. Project-owned
gates are correct answer-file bytes, matching vendor source/edition, explicit
SSD2 selection without guessing SSD1, production post-install execution and
actual recovery/security acceptance. Never reject a release merely because
no project-specific USB writer exists.

VirtualBox does not expose an attached virtual hard disk as the removable USB
flash class required by Setup's removable read/write implicit-search path. That
approach was tested and rejected: Windows saw the device but still displayed the
language page.

For the VM bench, use Microsoft's separate supported **removable read-only
media** discovery path instead. The harness builds a tiny Joliet answer DVD and
must prove before boot that:

- a Joliet supplementary volume descriptor is present;
- the Joliet root exposes exactly `Autounattend.xml`;
- the XML itself passes the full install contract;
- the answer DVD is separate from and does not modify the official Microsoft
  installation ISO.

The ISO9660 primary namespace may contain the 8.3-compatible
`AUTOUNAT.XML;1`; Windows Setup must receive the exact long name from Joliet.
This distinction is empirically material: the non-Joliet answer DVD was ignored,
while the corrected Joliet DVD suppressed the language-selection page and
entered unattended Setup.

Thus VM and production use the same Windows **implicit answer-file discovery**
semantics and the same rendered product contract, while the removable-media
class differs only because of VirtualBox's device model.

The stock Microsoft optical image intentionally has a timed "Press any key to
boot from CD or DVD" gate. The VM uses VirtualBox `USBKeyboard` because the
SOAP keyboard path was empirically shown not to reach this UEFI prompt through
the PS/2 HID configuration. The harness detects the one-line optical prompt
from framebuffer geometry and then sends exactly one **Enter** make/break pair
through `IKeyboard.putScancodes`. If the prompt is not observed, it sends no
key and fails closed. This exception is boot orchestration only;
keyboard/scancode injection remains forbidden as a guest automation or command
transport, and no keys are sent during Windows Setup/OOBE.

The old VM had exactly one synthetic destructive target, so its resolved `DiskID=0`
proves answer-file mechanics only. A production renderer must not silently reuse
that binding on the two-SSD ASUS.

### Business-requirement coverage by provisioning phase

Every authoritative requirement in `BUSINESS_REQUIREMENTS.md` has an explicit
owner. "Not in Autounattend" is intentional where the requirement belongs to a
later or hardware-specific trust boundary.

| BR | Owner |
|---:|---|
| 1 | hardware architecture; ASUS binding is allowed |
| 2 | user-selected RAID virtual disk; SSD1 Offline; independent target-local ESP/WinRE |
| 3 | product/trust architecture, not an install-page setting |
| 4 | post-install isolation + VBS/vault/Ledger boundaries |
| 5 | TPM/Pluton/VBS design and bare-metal validation |
| 6 | UEFI/Secure Boot at install plus BitLocker/Secure Launch post-install |
| 7 | BitLocker post-install on each relevant OS volume |
| 8 | independent volume protectors; no cross-OS auto-unlock |
| 9 | BitLocker TPM + startup PIN post-install |
| 10 | startup PIN distinct from Hello/ESS credentials |
| 11 | Hello/ESS bare-metal gate |
| 12 | VBS credential-broker/vault gate |
| 13 | trusted-context/transaction-confirmation architecture |
| 14 | accepted v1 trusted-context compromise + phase-2 display |
| 15 | Ledger/YubiKey remain independent hardware trust domains |
| 16 | offline BitLocker/vault recovery material + independent token path |
| 17 | official media + reproducible install/configuration/audit |
| 18 | known-good external recovery/install media + offline recovery material |
| 19 | Setup can begin offline; network is allowed after the fresh OS runs |
| 20 | post-install maintenance/sensitive-work gate |
| 21 | Windows Update/OEM/Google supported maintenance channels |
| 22 | supported Windows security mechanisms; minimal custom plumbing |
| 23 | Autounattend + desired-state configuration + machine-readable audit |
| 24 | VM evidence and ASUS bare-metal evidence remain separate |
| 25 | interactive target selection + SSD1 Offline; never an unconfirmed automatic wipe |
| 26 | Microsoft ISO provenance + vendor-origin software channels |
| 27 | post-install Chrome/wallet/Ledger/Hello workload validation |
| 28 | product outcome/economics may replace a mechanism without weakening requirements |
| 29 | TPM + offline recovery key protection immediately; owner startup PIN after Setup |
| 30 | enforce Windows 11 Administrator Protection, reboot and verify live behavior |
| 31 | physical ASUS VBS/HVCI firmware UEFI Lock after verified runtime and recovery |
| 32 | offline and networked Windows Sandbox profiles, read-only narrow input |
| 33 | internet-only Sandbox network acceptance with host/LAN/VPN blocking |
| 34 | connection-process/destination observation and host-side deny/prompt |
| 35 | Edge everyday, Chrome sensitive; official wallets, KeePass and Ledger |
| 36 | owner-provided USB, interactive RAID selection, ESP/MSR/C:/WinRE layout, postinstall acceptance |

### Account and OOBE contract

The unattended path must avoid making a Microsoft Account a prerequisite for
installation. Use supported Windows unattended/OOBE mechanisms to suppress the
Microsoft Account requirement where the installed build exposes such controls.

A local account may be created by supported unattended means when that is
required to complete automated setup and establish the post-install automation
boundary.

Production secrets must **never** be embedded in `Autounattend.xml`, auxiliary
answer media, repository files, VM run artifacts or logs. VM-only throwaway
credentials are test infrastructure and must remain outside Git. They are not
the production credential design.

### Production physical installation

The physical provisioning flow is:

```text
verify official Microsoft ISO
        ↓
create trusted installation media + Autounattend.xml
        ↓
boot WinPE/Setup
        ↓
identify existing SSD1 in WinPE and place it Offline
        ↓
show user the RAID virtual disks and obtain an explicit target selection
        ↓
verify selected target is writable and protected SSD1 remains Offline
        ↓
prepare GPT: ESP(300) + MSR(16) + C:(capacity minus WinRE) + WinRE(2048)
        ↓
install Windows 11 Pro (non-N) to the selected C: partition
        ↓
verify target-local ESP/WinRE, WinRE registration and no SSD1 dependency
        ↓
apply en-US UI + US/Russian input + Germany formats + W. Europe timezone
        ↓
complete supported local-account/OOBE path
        ↓
first usable desktop
        ↓
supported drivers + Windows Update
        ↓
apply declarative desired state
        ↓
enable/configure BitLocker TPM+PIN
        ↓
configure Hello/ESS and security features
        ↓
install workload software
        ↓
run machine-readable audit
```

RAIDXpert2 is already accepted as the allocation architecture. The RAID
hardware experiment, separately tracked from this Setup issue, proves that
the ASUS actually exposes independent expandable virtual disks without
compromising Home. The installation target above is the owner-selected
single-disk virtual disk on Lexar SSD2. Setup/deployment owns the target-local
ESP/MSR/WinRE/Windows partition layout. SSD1 must not become a boot/storage
member of the Pro environment.

Network availability is not required to **begin** trusted installation.

Network use after the fresh OS is running is acceptable and desirable for
supported Windows updates, drivers, activation and vendor software.

Any change to install-time disk layout, boot configuration, edition selection,
answer-file/OOBE behavior or other pre-desktop semantics must be validated by a
**clean reinstall** of the disposable VM. Do not mutate a previously installed
VM and call that installation-path evidence.

### Declarative post-install configuration

After the clean unattended install reaches a usable desktop, ordinary
configuration iteration should happen from snapshots rather than by repeating
the complete Windows installation.

The preferred post-install mechanism is supported **WinGet Configuration / DSC**
desired state where the required resource exists. PowerShell is a supported
implementation/interface tool, but it is not a license to turn the
configuration into one giant imperative bootstrap script.

Specific rules:

- install/update PowerShell to the **latest supported stable release**
  declaratively through the selected supported package/configuration path;
- use first-party or otherwise supported DSC/WinGet Configuration resources
  where they express the desired state;
- do **not** hide arbitrary imperative PowerShell inside generic DSC `Script`
  resources and describe the result as declarative;
- keep vendor-owned maintenance on vendor-supported channels: Windows Update
  for Windows, the official Google channel for Chrome, and supported OEM/vendor
  mechanisms for device software;
- use imperative code only for a demonstrated residual gap that cannot be
  represented reasonably by supported desired-state mechanisms;
- keep that residual code narrow, explicit and auditable.

Manual GUI steps should exist only when the product deliberately requires user
presence or no supported automation interface exists.

The VM bench must therefore prove two distinct boundaries:

```text
official ISO + Autounattend.xml
        ↓
clean reproducible Windows desktop
        ↓
snapshot
        ↓
WinGet Configuration / DSC desired state
        ↓
audit
```

Install/boot-path changes require rebuilding from the first boundary.
Post-install desired-state changes may iterate from the clean snapshot.

## VirtualBox development bench

Issue #6 owns the initial Windows VM bench.

The bench deliberately uses the existing **Oracle VirtualBox SOAP/WebService**
control path.

**Hyper-V is not a dependency of the bench.**

This is an economics decision: the existing runner already has a working
VirtualBox control plane, snapshot lifecycle and automation experience.

### VM goals

The canonical VM should use UEFI firmware and, where the installed VirtualBox
SOAP/WebService stack supports them meaningfully, virtual TPM 2.0 and Secure
Boot. Their presence in the VM is useful for exercising configuration paths but
is not promoted into proof of the physical ASUS trust boundary.

The VM should prove:

- official ISO boot and unattended Windows 11 Pro installation;
- repeatable disk/layout automation;
- repeatable post-install configuration;
- browser/software install logic;
- **elevated** in-guest audit of actual Secure Boot state, TPM 2.0 readiness
  and specification, target-local GPT partitions, WinRE enabled/location,
  BitLocker encryption versus actual TPM+PIN/recovery protectors, and
  Administrator Protection policy; missing elevation is an audit failure,
  never a silent WARN or a successful audit;
- separate VBS/HVCI configuration-policy read-back from runtime proof (the
  current VirtualBox Hyper-V/NEM backend cannot validate VTL1 runtime);
- update/reboot automation;
- snapshot/reset/rebuild lifecycle;
- BitLocker policy flow to the extent VirtualBox presents a meaningful TPM;
- VBS/HVCI/Administrator Protection policy configuration where possible;
- VBS-enclave development/build/unit behavior that can run in the VM.

### VM control rules

- control VirtualBox through the existing SOAP/WebService API;
- do not assume `VBoxManage` is the control plane;
- guest work should run through repository harness/supported Windows guest
  automation;
- do not inject ad-hoc guest commands through Desktop Commander;
- Desktop Commander is acceptable for host filesystem/repository work;
- use snapshots aggressively;
- do not reinstall the VM for ordinary iteration when a clean checkpoint is
  available;
- a destructive install run must persist its stage outside the harness process;
  after the initial optical boot has succeeded, `await-guest-control` and
  `base-checkpoint` are resumable boundaries so a host/harness restart does not
  require another disk wipe;
- resume must fail closed for ambiguous earlier stages rather than repeating a
  destructive action;
- while waiting for the first usable desktop, persist a read-only heartbeat with
  VM state, Guest Additions state, Guest Control readiness and VDI size/mtime so
  a stuck Windows Setup is diagnosable without injecting guest commands;
- keep the VM network adapter disabled throughout Setup and OOBE; enable NAT
  only after the powered-off `installed-clean` checkpoint, immediately before
  post-install bootstrap/update work;
- do not request nested hardware virtualization for the installation bench by
  default. VBS/nested-virtualization experiments belong to the later security
  validation stage, especially when VirtualBox itself is running through the
  Windows Hyper-V/NEM backend;
- if the VirtualBox bench remains Running with no VDI progress before Guest
  Control becomes available, record the stall evidence and permit one VM-only
  cold restart of the existing VDI without optical boot. A repeated stall is
  a hard failure; never turn this recovery into a destructive reinstall;
- allow only one install/resume controller process for the active run;
- clean old VMs/snapshots/cache artifacts so disk consumption remains bounded.

### What the VM cannot prove

The VM is not acceptance evidence for:

- real Microsoft Pluton behavior;
- the physical ASUS TPM/PCR behavior;
- ESS Face / ACPI SDEV camera path;
- real Windows Hello biometric isolation on the ASUS;
- AMD Secure Launch/DRTM on the physical CPU/firmware;
- physical dual-SSD boot independence;
- real Ledger USB/WebHID behavior;
- real YubiKey hardware behavior;
- production VBS/VTL1 resistance on the target hardware if nested
  virtualization/emulation is incomplete.

If VirtualBox cannot expose a feature faithfully, record the limitation and move
the claim to the bare-metal gate. Do not construct a mock test that merely says
PASS.

## Machine-readable audit

The same audit framework should run in VM and on bare metal.

Output should be structured and should separate:

- PASS;
- FAIL;
- NOT_APPLICABLE / NOT_PROVABLE_IN_VM;
- informational evidence.

At minimum capture:

- Windows edition/build;
- activation status (informational, not a security gate);
- UEFI/Secure Boot state;
- TPM presence/type and relevant readiness where queryable;
- BitLocker encryption/protectors without exposing recovery secrets;
- disk/partition/ESP/WinRE layout;
- VBS state;
- HVCI / Memory Integrity state;
- Secure Launch state;
- Windows Hello/ESS evidence;
- Windows Biometrics event evidence relevant to ESS;
- Administrator Protection state;
- Defender state;
- Firewall state;
- browser/software versions;
- pending update/reboot state;
- sensitive-work gate result.

The audit must never print:

- BitLocker recovery passwords;
- Hello PIN;
- startup PIN;
- vault master K;
- YubiKey PIN;
- wallet seeds/private keys;
- service passwords.

## Validation methodology

Do not confuse "configured" with "works".

Use two kinds of evidence:

1. **configuration/state evidence** — the effective policy or state is present;
2. **behavioral evidence** — the live system demonstrates the intended result.

Examples:

- BitLocker protector enumeration is configuration/state evidence;
- booting and observing a real startup-PIN prompt is behavioral evidence;
- an ESS-related registry value is not enough;
- Windows Biometrics event 1108 showing VSM isolation is runtime evidence;
- a VBS enclave API unit test is not proof that physical ASUS DRTM is active.

Use authoritative product documentation to determine expected behavior first,
then perform one meaningful end verification. Avoid repeated "try a step, see
what breaks, research the next step" loops when the supported sequence can be
determined in advance.

## Bare-metal acceptance gates

After VM configuration converges, validate on the ASUS:

1. SSD2 has independent GPT/ESP/WinRE.
2. Pro boots without SSD1 being part of its required boot chain.
3. SSD1 Home remains independently bootable/recoverable.
4. Secure Boot is active.
5. BitLocker is active on Pro with TPM + startup PIN.
6. BitLocker recovery path works from offline recovery material.
7. Home and Pro OS volumes are not automatically unlocked by booting the other
   installation.
8. VBS is active.
9. HVCI / Memory Integrity is active.
10. Secure Launch/DRTM is active when supported by the final ASUS
    firmware/Windows configuration.
11. ESS Face remains active on the built-in camera.
12. Windows Biometrics event 1108 again shows the face path isolated in Virtual
    Secure Mode.
13. Windows Hello Face works for normal in-OS user verification.
14. distinct Hello PIN fallback works.
15. Administrator Protection works with the selected Hello authorization path
    when supported by the installed build.
16. Chrome sensitive profile works.
17. required wallet extensions work.
18. Ledger works on the real USB path.
19. transaction-signing workflow leaves private keys on Ledger.
20. Windows Update/reboot preserves BitLocker, VBS, ESS and normal workstation
    usability.
21. machine-readable final audit passes all production-applicable checks.

The VBS credential broker/vault gets its own PoC and security-review gate before
it becomes responsible for real credentials.

## VBS vault PoC acceptance gates

The PoC is successful only if it demonstrates all of the following:

1. K is generated from a supported CSPRNG.
2. K is not returned to VTL0.
3. no bulk secret export API exists.
4. a host process cannot directly read enclave secret memory.
5. one record can be released through the narrow API.
6. fresh user-bound authorization is required for release.
7. the enclave does not trust a bare host boolean asserting Hello success.
8. hostile/repeated/replayed host calls are handled according to explicit
   policy.
9. sealing identity is restrictive and documented.
10. update/version/anti-rollback handling is designed before production use.
11. recovery with an independent hardware factor is demonstrated without the
    original ASUS TPM if recovery is part of the PoC.
12. the test documentation clearly states that plaintext released into Chrome
    can be stolen by a compromised VTL0 at use time.
13. the trusted-context/confused-deputy limitation is explicitly recorded.

Do not put real production passwords in the PoC.

## Non-goals / rejected baseline choices

The following are not part of the initial production architecture:

- Linux as the production daily workstation;
- portability of the complete OS between arbitrary PCs;
- Hyper-V as the VM test-bench dependency;
- Windows 11 Pro N;
- reseller-provided Windows ISO images;
- activation cracks or scripts;
- a permanently elevated daily administrator session;
- reusing the BitLocker startup PIN as the normal Hello/application PIN;
- using KWallet/desktop software storage as the root of credential security;
- tpm2-pkcs11-style custom PIN storage as a Hello replacement;
- building a full custom password manager;
- building a custom Windows Credential Provider in v1;
- requiring YubiKey for every daily login;
- requiring the existing Rutoken for the new architecture;
- treating Secure Desktop as protection against hostile VTL0 kernel;
- claiming Administrator Protection itself is VBS-resident without evidence;
- buying Enterprise merely for Credential Guard;
- treating WDAC as a solution to malicious browser extensions;
- trusting host process identity as an enclave security boundary;
- storing Ledger wallet private keys in browser extensions;
- enabling blind signing by default;
- making external trusted display a v1 blocker.

## Accepted compromises

The architecture consciously accepts:

- the complete OS is bound to the primary ASUS rather than portable;
- a specific password legitimately released to Chrome can be stolen by a
  sufficiently compromised VTL0 at the moment of use;
- ESS/Hello proves presence/identity but not arbitrary application-specific
  transaction context;
- version 1 has residual confused-deputy risk until trusted semantic display is
  added;
- physical firmware compromise remains outside what VBS/DRTM alone can fully
  neutralize;
- a VM cannot prove physical security boundaries;
- YubiKey recovery introduces a separate physical object that must be stored
  safely;
- clean rebuild is preferred over trying to preserve a compromised OS instance.

These compromises are accepted because they preserve the stronger and more
valuable properties without turning the workstation into a custom operating
system/security-platform project.

## Implementation order

1. Maintain the Windows business requirements and this architecture as the
   authority for implementation choices.
2. Complete issue #6: repeatable VirtualBox Windows 11 Pro bench using the
   existing SOAP/WebService path.
3. Build unattended installation/configuration and a reusable structured audit
   in the VM.
4. Use snapshots to converge the configuration economically rather than
   repeatedly reinstalling.
5. Install Windows 11 Pro on SSD2 of the ASUS with SSD1 offline during Setup.
6. Establish BitLocker TPM+startup-PIN, Secure Boot, VBS, HVCI, Secure Launch
   where supported, Windows Hello/ESS Face and Administrator Protection.
7. Validate the bare-metal gates once the supported configuration is complete.
8. Install/configure Chrome sensitive profile and validate Ledger + required
   wallet extensions.
9. Build the minimal VBS credential-broker PoC using fake credentials.
10. Select the exact YubiKey model/interface and prove independent vault
    recovery.
11. Decide whether the VBS broker provides enough incremental security to
    justify production use; do not force it into production merely because the
    PoC exists.
12. Research/implement the external trusted display/button protocol as phase 2
    if the residual context-spoofing risk justifies the cost.

## External architecture references

The implementation should continue to use authoritative vendor documentation as
the source for detailed platform behavior, including:

- Windows Hello / Enhanced Sign-in Security:
  https://learn.microsoft.com/windows-hardware/design/device-experiences/windows-hello-enhanced-sign-in-security
- Microsoft Pluton:
  https://learn.microsoft.com/windows/security/hardware-security/pluton/microsoft-pluton-security-processor
- VBS enclaves:
  https://learn.microsoft.com/windows/win32/trusted-execution/vbs-enclaves
- Windows boot / Trusted Boot:
  https://learn.microsoft.com/windows/security/operating-system-security/system-security/trusted-boot
- BitLocker:
  https://learn.microsoft.com/windows/security/operating-system-security/data-protection/bitlocker/
- Windows security / VBS and HVCI:
  https://learn.microsoft.com/windows-hardware/design/device-experiences/oem-vbs
