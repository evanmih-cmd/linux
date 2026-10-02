# Portable workstation — architecture

## Status and authority

This document defines the current technical architecture for the portable
workstation.

The authoritative product requirements are in
[`BUSINESS_REQUIREMENTS.md`](BUSINESS_REQUIREMENTS.md). If this architecture
conflicts with a business requirement, the requirement wins and the architecture
must change.

The architecture is intentionally product-first and economy-first:

- **Product First** is an ordering rule, not a ban on custom work. Evaluate and
  exhaust supported production product mechanisms before designing an
  owner-built substitute. Prefer distribution defaults when they satisfy the
  requirements, because they usually reduce lifecycle cost and uncertainty.
- **Economy First** is a cost rule, not a component-count rule. Among solutions
  that satisfy the authoritative requirements, compare total lifecycle cost:
  implementation effort, recurring administration, maintenance/debugging,
  infrastructure/capital cost, upgrade burden, recovery burden and expected
  operational loss from failure. Fewer components or less custom code matter
  only insofar as they reduce that total cost.
- Custom code, patches, image customization or additional components are
  legitimate candidates when their total lifecycle cost is lower than the
  available product alternatives while still satisfying the requirements.
- A product mechanism does not win merely because it is built in; product
  mechanisms get evaluated first. Conversely, a custom mechanism is not
  rejected merely because it is custom.
- beta, preview, RC, experimental, or test-only features are not part of the
  production critical path unless the business requirements are explicitly
  changed to accept that risk/cost.

The current design is ready for implementation validation in a VM. Hardware-
specific behavior is called out explicitly where it still requires proof on the
primary ASUS host.

## Architecture freeze

**Frozen baseline: 2026-10-02.**

The choices in this document are implementation constraints, not suggestions.
A VM result, installer default, convenience argument, or alternative that is
merely easier to test does **not** silently replace them.

In particular, the frozen critical-path choices are:

- platform: openSUSE Tumbleweed;
- boot: Secure Boot through the supported shim + systemd-boot/BLS/sdbootutil
  path, with removable fallback boot artifacts and no persistent host boot-order
  dependency;
- root encryption: LUKS2 using the supported systemd-FDE path;
- root filesystem and snapshot layer: **Btrfs + Snapper**;
- system-update transaction layer: **transactional-update on Btrfs snapshots**;
- persistent user/application state: Btrfs-backed state excluded from normal
  root rollback according to the supported Tumbleweed layout;
- provisioning: verified official Offline ISO plus a separately verifiable
  Desktop-Linux OEMDRV/AutoYaST layer;
- target selection: exact persistent target identity and fail-closed behavior;
- **no LVM, LVM-thin, ZFS, mdraid, or second snapshot/storage abstraction in
  the portable root stack.**

A frozen choice may be changed only when:

1. a business requirement changes, or live evidence proves the frozen design
   cannot satisfy an existing requirement;
2. the conflict and alternatives are recorded in GitHub issue #1;
3. Product First and Economy First are re-evaluated against the concrete
   evidence;
4. `ARCHITECTURE.md` is changed in a dedicated architecture-decision commit
   **before** implementation proceeds on the replacement design.

Until such a commit exists, test failures are implementation/provisioning
problems to solve within this architecture, not permission to substitute a
different storage or boot stack.

## Hardware and workload baseline

Primary host:

- ASUS TUF A14 FA401EA;
- AMD Ryzen AI Max+ 392;
- Radeon 8060S / gfx1151;
- 64 GB RAM;
- removable SSD containing the complete portable workstation;
- Windows/internal storage and host firmware configuration remain outside the
  workstation's authority.

The workload is intentionally narrow:

- browser-centric sensitive operations;
- persistent browser profile and required extensions/application state;
- potentially irreversible high-value actions;
- external owner-controlled USB/HID authorization device;
- no requirement to optimize for unrelated desktop applications.

The workstation is expected to run normally on the primary host. Portability to
another compatible host is an emergency recovery capability, not a routine
daily host-switching workflow.

## Selected platform

The selected platform is **openSUSE Tumbleweed**.

Reasons:

- current production kernel/userspace appropriate for the new AMD platform;
- native desktop/browser workload without VM or USB-forwarding layers;
- LUKS2, Btrfs and Snapper are normal distribution mechanisms;
- current Tumbleweed EFI installations use the BLS/systemd-boot stack managed
  by `sdbootutil`;
- TPM2 measured-FDE integration is distribution-supported;
- `transactional-update` provides atomic snapshot-based system updates;
- the provisioning mechanism remains an explicit open gate: the final path must be offline, declarative, non-destructive to the host, NVRAM-safe, and compatible with the selected Secure Boot / measured-unlock architecture;
- the design does not require enterprise management infrastructure or
  additional specialized hardware.

Rejected alternatives and the research history are kept in GitHub issue #1;
they are not repeated here.

## Trust and boot model

### Normal primary-host path

The normal boot path is:

```text
ASUS UEFI firmware
        ↓
Secure Boot
        ↓
shim
        ↓
systemd-boot / BLS path managed by sdbootutil
        ↓
measured kernel + initrd + command-line state
        ↓
TPM2 policy + owner PIN
        ↓
LUKS2 unlock
        ↓
Btrfs system
        ↓
startup maintenance gate
        ↓
sensitive workload
```

The TPM-bound path is the accepted normal unlock mechanism on the primary host.

If pre-unlock state covered by the TPM policy changes unexpectedly, normal TPM
unlock must fail. An unexpected plain LUKS passphrase prompt on the primary
host is not part of the trusted normal workflow.

### Emergency portability path

The removable SSD also retains an ordinary owner-held LUKS passphrase.

Its purpose is emergency recovery when the primary host is unavailable:

```text
compatible replacement host
        ↓
boot removable SSD explicitly
        ↓
primary-host TPM policy unavailable
        ↓
owner LUKS passphrase
        ↓
same encrypted workstation state
```

The passphrase is the portability credential. TPM recovery material does not
replace it.

This emergency path has a deliberately lower pre-unlock assurance level than
the enrolled primary-host TPM path because the replacement host has no
pre-existing measured policy for this workstation. That reduction is accepted
as an emergency-recovery compromise rather than treated as a normal operating
mode.

### Removable boot and host isolation

The workstation must be self-contained on the removable SSD.

Required behavior:

- user explicitly selects the removable SSD from the firmware one-time boot
  menu;
- the external ESP carries the standard removable fallback entry:
  `EFI/BOOT/BOOTX64.EFI`;
- no internal disk or internal ESP is part of the portable storage graph;
- no persistent UEFI boot entry is required;
- installer/runtime configuration uses `updateNvram=false` /
  `UPDATE_NVRAM=no`;
- `BootOrder` and `BootNext` are not used as a convenience mechanism.

When the removable SSD is absent, the host follows its normal Windows boot
behavior without repair or restoration.

## Storage and state model

### Frozen storage graph

The selected storage model is:

```text
removable SSD
└── GPT
    ├── EFI System Partition (unencrypted boot partition)
    │   └── shim / systemd-boot / BLS boot artifacts
    ├── LUKS2 root container
    │   └── Btrfs
    │       ├── root/system state
    │       │   └── Snapper + transactional-update snapshots
    │       └── persistent user/application state
    │           └── excluded from normal root rollback by the supported layout
    └── encrypted swap when created by the supported Tumbleweed guided layout
```

**There is no LVM layer in this graph.** Btrfs is both the root filesystem and
the snapshot substrate. Snapper and `transactional-update` operate on Btrfs
snapshots; LVM snapshots are neither required nor permitted by the frozen
architecture.

### LVM decision record

LVM has been considered twice and rejected twice:

1. In the earlier Ubuntu/Subiquity prototype it was introduced because Curtin
   could express LVM/ext4 preserve/reformat boundaries declaratively while it
   could not express the desired Btrfs-subvolume lifecycle. That changed the
   architecture to fit the installer and was reverted as an implementation
   error.
2. During the later openSUSE/Agama design work LVM was reconsidered in
   discussion as a convenient declarative state/snapshot separation mechanism.
   The committed Agama VM profile itself did not encode LVM: it delegated to
   Tumbleweed `partitions: default` under LUKS2. The LVM idea was nevertheless
   another installer-driven design detour and was not accepted. Tumbleweed
   already provides Btrfs/Snapper as its native snapshot/recovery layer, and
   `transactional-update` is built around Btrfs snapshots. Adding LVM would
   duplicate the storage/snapshot abstraction without satisfying a requirement
   that Btrfs cannot satisfy.

Neither episode establishes an LVM requirement. Reintroducing LVM requires the
architecture-unfreeze process above and concrete evidence that the frozen
Btrfs/Snapper design cannot satisfy an authoritative requirement.

The installer may choose partition sizes appropriate to the physical target and
may create encrypted swap according to the supported Tumbleweed guided layout.
Those sizing details do not change the storage architecture. The VM proof's
observed ESP + LUKS2/Btrfs root + encrypted-swap layout is therefore an
implementation of this graph, not a new architecture.

Required invariants:

- only the removable SSD contains required workstation state;
- user/browser state must not roll back automatically with a system rollback;
- root/system state uses Btrfs snapshots for recovery;
- Snapper rollback and transactional updates share the Btrfs snapshot layer;
- snapshots are rollback points, not backups;
- no LVM, LVM-thin, ZFS, mdraid, or additional snapshot/storage abstraction is
  introduced without first unfreezing the architecture through the process
  defined above;
- do not recreate the earlier owner-designed Ubuntu subvolume topology merely
  for aesthetic symmetry; use the supported Tumbleweed Btrfs/Snapper layout.

Normal browser profile and user state should live in the distribution-supported
persistent user-state area (normally `/home`) rather than in a custom
persistence framework.

## Provisioning

### Two-layer installation medium

The production provisioning model is a **verified upstream base plus a
separately verifiable Desktop-Linux layer**.

The two logical layers are:

```text
Layer 1 — immutable upstream base
  official openSUSE Tumbleweed Snapshot20260930 Offline Image
  verified before deployment from openSUSE-signed checksum metadata
  expected ISO SHA-256:
  0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99

Layer 2 — Desktop-Linux provisioning delta
  AutoYaST profile
  installer-only files required by the profile
  minimal version-specific YaST correction, while upstream requires it
  complete manifest containing hashes of every owned file
```

The upstream ISO is not rebuilt merely to carry Desktop-Linux configuration.
Its cryptographic identity is established on the downloaded ISO before it is
written to installation media.

For VM development and validation the two logical layers are deliberately
presented as two media:

```text
VirtualBox optical medium
  verified official Snapshot20260930 ISO
        +
small Desktop-Linux layer medium
  mutable during development
```

This avoids repeatedly rebuilding and hashing a 4.4 GiB derived ISO when only
the Desktop-Linux profile or installer delta changed.

The production physical medium is one writable USB device. Deployment is:

1. verify the official ISO cryptographically;
2. write that verified ISO to the USB device with a normal image-writing tool
   such as Rufus;
3. add the independently constructed and verified Desktop-Linux layer to the
   same writable USB device;
4. verify the Desktop-Linux layer from its manifest.

Physical co-location does not collapse the trust boundaries. The base is
identified by the verified upstream ISO; the custom layer is identified by its
complete manifest. A whole-device hash after adding the custom layer is not a
substitute for those two independent identities.

### Provisioning requirements must be satisfied together

The combined physical installation medium must simultaneously provide:

- a supported production/GA Tumbleweed installation base;
- all baseline packages on the upstream Offline Image, so provisioning and
  bare-metal recovery work with networking unavailable;
- the declarative unattended profile on the same physical USB medium;
- unambiguous persistent identity of the removable target;
- fail-closed behavior when that exact target is absent;
- no writes to the host internal disk or ESP;
- no persistent host NVRAM/BootOrder mutation;
- the selected Secure Boot + BLS boot architecture;
- LUKS2 with owner recovery passphrase and TPM2+PIN primary-host unlock;
- a complete manifest of the Desktop-Linux layer;
- repeatable independent verification of both logical layers.

A candidate that misses any one of these is not the production provisioning
path.

### Tumbleweed Offline Image + AutoYaST

The official Tumbleweed Offline Image is the immutable upstream base. YaST /
AutoYaST remains the provisioning mechanism.

The Desktop-Linux profile owns the persistent target identity and policy
inputs, while storage topology remains delegated to the normal Tumbleweed
guided proposal for that one selected drive. Snapshot20260930 product defaults
provide `systemd_fde`, `argon2id`, `tpm2+pin`, Btrfs and Snapper.

Three small installer-time gaps remain in Snapshot20260930:

- the installer runtime lacks `keyctl`, required to place the separately
  entered TPM2 PIN into the sdbootutil-specific kernel keyring entry;
- the systemd-boot AutoYaST importer omits `global/update_nvram`, although the
  runtime bootloader object supports the setting;
- when AutoYaST writes a NetworkManager target configuration with
  `apply_config=false`, `Lan.Write` still waits for a running network and raises
  a modal `No network running` error. That is inappropriate for the offline
  target-chroot write path and breaks unattended installation.

The Desktop-Linux layer therefore currently owns:

```text
autoinst.xml
stock keyctl + libkeyutils from the same verified Snapshot20260930 DVD
minimal installer-only AutoYaST importer correction for update_nvram=false
minimal installer-only NetworkManager target-write correction
manifest of all layer files and hashes
```

No installed Tumbleweed package is forked or replaced. Both YaST corrections
are installer-only, version-specific, and must be deleted when upstream supplies
the required behavior. The network correction preserves the product-selected
NetworkManager backend; it only suppresses the running-network check when YaST
was explicitly asked to write target configuration without applying it.

The exact supported installer-side transport for the separate local layer is a
live proof item. The architectural requirement is the two-layer trust model;
it does not require repacking the upstream ISO.

### Development and release workflow

Routine development iterations rebuild only the small Desktop-Linux layer:

```text
edit profile / installer delta
        ↓
rebuild small layer
        ↓
verify layer manifest
        ↓
boot verified official ISO + layer in VirtualBox
        ↓
run provisioning gates
```

A monolithic derived ISO may still be built as a diagnostic or archival
artifact, but it is not the source of truth and is not required for each
iteration.

The release source of truth is the exact upstream ISO identity plus the exact
Desktop-Linux layer manifest and its source-controlled inputs. This is both the
VM proof model and the physical-USB model; only physical placement differs.

### Agama status

Agama remains useful research history, but the public Agama Live ISO previously
evaluated is a development/testing image and does not provide the required
complete offline product repository. It is not the current production path.

### Declarative preference

The validated AutoYaST profile is the authoritative provisioning input.
Custom installer-time logic is limited to irreducible product gaps and must be
small, manifestable, version-bound and independently verifiable.

The obsolete Ubuntu/Subiquity LVM/ext4 installer profiles have been removed
from the current tree. Their history remains available in git, but they are not
implementation artifacts for this architecture.

## System update model

### Mandatory startup maintenance gate

Sensitive work is never released directly after boot.

Every startup enters the maintenance policy first:

```text
boot and unlock
        ↓
network available
        ↓
transactional-update dup
        ↓
transaction successful?
   ├── no  → recovery/admin available; sensitive workload blocked
   └── yes
        ↓
activate updated snapshot using the minimum trusted restart level
        ↓
validate the running state
        ↓
report explicit maintenance result
        ↓
release sensitive workload
```

The user must receive a clear outcome:

- already current;
- updated successfully;
- update failed.

Admin/recovery access may remain available after failure. Only the sensitive
workload is gated.

### Why transactional-update

`transactional-update` is preferred over live in-place package replacement for
the mandatory startup cycle because it:

- performs the update in a new Btrfs snapshot;
- leaves the currently running root untouched during the transaction;
- discards a failed transaction snapshot;
- uses `zypper dup` for Tumbleweed;
- provides a deterministic rollback boundary before the new state is activated.

The usual warning that changes made to the old running root after creating the
transaction snapshot can be lost is acceptable here because the startup gate
does not release the working session between update creation and activation.

Do not run multiple independent transactional updates before activation unless
the product-supported continuation semantics are explicitly used.

## Restart policy

### Userspace-only changes

Allow systemd soft reboot when the package manager reports that it is
sufficient.

The updated snapshot is prepared as the next root and the userspace is rebuilt
without firmware re-entry:

```text
updated snapshot
        ↓
/run/nextroot
        ↓
systemd soft-reboot
        ↓
fresh userspace on updated root
```

This removes stale processes/inodes before sensitive work begins while avoiding
an unnecessary trip through host firmware.

### kexec

**kexec is disabled.**

It does not reproduce the complete firmware -> shim -> bootloader
Secure-Boot/measured-boot chain. Kernel signature enforcement under lockdown is
not treated as equivalent to a fresh platform boot for this workstation.

Configure transactional-update/tukit so that kexec is not an allowed restart
method.

### Full reboot

A kernel-level transition that cannot be satisfied by soft reboot requires a
full reboot through firmware.

Do not use `BootNext`, `BootOrder` or another persistent host-firmware
mutation to force re-entry into the removable workstation.

Whether the ASUS FA401EA naturally returns to the selected removable device on
a warm/full reboot after one-time boot selection is a hardware validation item.
If it does not, manual one-time boot selection is the acceptable fallback
unless a supported non-persistent firmware mechanism is proven.

## Rollback and system replacement

Btrfs/Snapper is the supported recovery mechanism for normal system failure.

A failed update or broken system state must be recoverable by selecting or
rolling back to a known-good root snapshot without rolling normal user/browser
state back with it.

This satisfies the business requirement to replace system state with a
known-good state. A reinstall is not the normal recovery primitive.

A clean redeployment remains an emergency option when snapshots themselves are
unavailable or no longer trusted. That operation must preserve required
persistent user/application state, but no separate owner-built reinstall
framework is part of the baseline architecture.

## Browser and external authorization device

Use a native Tumbleweed browser package so browser binaries participate in the
same managed RPM/update domain as the operating system.

Firefox vs Chromium is not an architectural preference. The final browser is
selected by the actual required web/API/device compatibility of the
owner-controlled USB/HID authorization device and target browser workload.

Do not introduce Flatpak, VM device forwarding, or custom udev/device middleware
unless the real device requires it.

## Maintenance policy state

The startup gate is policy glue, not a new updater.

Its responsibilities are limited to:

- trigger the supported transactional update;
- record the result for the current boot/update generation;
- prevent the sensitive workload target from starting until success is proven;
- keep a recovery/admin path available on failure;
- expose a clear success/current/failure result;
- allow the native update stack to perform soft or full reboot as configured;
- after restart, verify that the running snapshot is the successfully validated
  one before releasing the workload.

It must not duplicate package management, snapshot implementation, bootloader
management or TPM policy logic.

## Validation methodology

Validation follows the same product-first rule as the architecture itself.

Two different kinds of claims must be tested differently:

- **configuration invariants** are verified by reading the effective system
  configuration/state and proving that the required value is actually set;
- **behavioral invariants** are verified by exercising the live system and
  observing the required outcome.

A configuration assertion is not accepted as proof of runtime behavior, and a
self-referential test that only compares an expected value with the value used
to construct the test is not evidence.

Examples:

- bootloader selection, NVRAM-update policy, kexec enablement, filesystem
  layout, active systemd dependencies and TPM enrollment state are
  configuration/state checks;
- successful boot, failed-unlock behavior, snapshot rollback, update failure,
  soft reboot activation, workload blocking/release and persistence across
  restart are live behavioral tests.

Where a requirement has both a configuration and a behavioral dimension, both
must be checked independently.

## Validation gates

### VM proof required before implementation is considered proven

Using Oracle VirtualBox, validate the final selected provisioning path only after
it clears the product-level gates above:

1. baseline installation succeeds with VM networking disabled;
2. the installation medium itself supplies the unattended profile;
3. disk 0 models the ASUS internal disk and contains sentinel state; disk 1
   models the portable target; installation changes disk 1 and leaves disk 0
   unchanged;
4. no persistent firmware/NVRAM entry is created by provisioning;
5. UEFI Secure Boot works through the selected supported Tumbleweed boot path;
6. LUKS2 owner passphrase and TPM2+PIN primary unlock behave as designed;
7. Btrfs/Snapper snapshot and rollback semantics work;
8. transactional `dup` success and failure behavior works;
9. soft reboot activates qualifying userspace-only updates;
10. kexec remains disabled;
11. sensitive workload remains blocked until maintenance success while
    recovery/admin access remains available on failure.

VirtualBox cannot prove physical ASUS firmware behavior or real external-device
compatibility.

### Physical-host validation still required

On the ASUS TUF A14 FA401EA validate:

- Secure Boot + TPM2+PIN measured unlock;
- no internal disk/ESP/NVRAM mutation during real provisioning;
- removable `EFI/BOOT/BOOTX64.EFI` boot;
- behavior after a full reboot from a one-time external boot;
- the actual external USB/HID authorization device and selected browser;
- emergency passphrase access on another compatible physical host when
  practical.

## Accepted compromises

The architecture consciously accepts:

- emergency passphrase recovery on a non-enrolled host has lower pre-unlock
  assurance than normal TPM2+PIN operation on the primary host;
- a genuine firmware reboot may require manually selecting the removable SSD
  again if the ASUS firmware does not preserve the one-time selection;
- browser choice remains workload/device-driven until the actual authorization
  device is validated.

These are narrower compromises than introducing custom boot/signing,
firmware-mutation, enterprise-management or bespoke update infrastructure.

## Implementation order

1. Resolve the production provisioning gate without relaxing offline, host-isolation, measured-unlock or declarative requirements.
2. Prove that selected path in VirtualBox with networking disabled and an internal guard disk present.
3. Implement only the minimal systemd maintenance gate required to bind
   transactional-update to the sensitive workload target.
4. Validate the same artifacts on the physical removable SSD/FA401EA.
5. Validate the real browser + external authorization device.
6. Treat the architecture as production-ready only after the physical checks
   above pass.