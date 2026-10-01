# Portable workstation — architecture

## Status and authority

This document defines the current technical architecture for the portable
workstation.

The authoritative product requirements are in
[`BUSINESS_REQUIREMENTS.md`](BUSINESS_REQUIREMENTS.md). If this architecture
conflicts with a business requirement, the requirement wins and the architecture
must change.

The architecture is intentionally product-first and economy-first:

- use supported production capabilities before custom mechanisms;
- prefer distribution defaults when they satisfy the requirements;
- custom code is residual policy glue only;
- do not maintain a private PKI, custom bootloader, custom updater, bespoke
  installer framework, or owner-built kernel-signing lifecycle unless a real
  product gap is proven and consciously accepted;
- beta, preview, RC, experimental, or test-only features are not part of the
  critical path.

The current design is ready for implementation validation in a VM. Hardware-
specific behavior is called out explicitly where it still requires proof on the
primary ASUS host.

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
- Agama provides declarative unattended installation for Tumbleweed;
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

The selected storage model is:

```text
GPT
├── EFI System Partition
│   └── systemd-boot / shim / BLS boot artifacts
└── LUKS2
    └── Btrfs
        ├── root/system state managed with Snapper
        └── persistent user/application state outside root rollback
```

Use the Tumbleweed-supported Btrfs/Snapper layout unless a requirement proves a
need to diverge from it. Do not recreate the earlier owner-designed Ubuntu
subvolume topology merely for aesthetic symmetry.

Required invariants:

- only the removable SSD contains required workstation state;
- user/browser state must not roll back automatically with a system rollback;
- root/system state must have snapshot-based recovery;
- snapshots are rollback points, not backups;
- no LVM or ZFS layer is introduced without a requirement that Btrfs cannot
  satisfy.

Normal browser profile and user state should live in the distribution-supported
persistent user-state area (normally `/home`) rather than in a custom
persistence framework.

## Provisioning

### Installer

Use **Agama** for fresh unattended provisioning.

The installation profile must:

- select `Tumbleweed`;
- identify the destructive target unambiguously and fail if that identity
  cannot be established;
- configure only the selected removable SSD;
- create the required external ESP and encrypted Btrfs system;
- use LUKS2 with an owner passphrase;
- enable the supported TPM-backed unlock method for the primary host;
- set `bootloader.updateNvram=false`;
- install the Tumbleweed-selected EFI bootloader path;
- leave internal disks, internal ESPs and persistent firmware boot
  configuration untouched;
- install the packages/configuration required for the browser-centric workload
  and the mandatory startup maintenance flow.

The final profile must not identify the target with ambiguous rules such as
"first USB disk", "largest disk", or "first non-installer disk".

### Declarative preference

The Agama profile is the authoritative provisioning input.

Post-install scripts are allowed only for a capability Agama cannot express
declaratively and only after that product gap is documented. A script must not
be used merely because it is quicker to write than learning the supported
declarative mechanism.

The old `autoinstall-fresh.yaml` and `autoinstall-reinstall.yaml` files are
legacy Ubuntu/Subiquity experiments. They are not valid implementation
artifacts for this architecture.

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

## Validation gates

### VM proof required before implementation is considered proven

Using Oracle VirtualBox, validate:

1. unattended Agama installation to a dedicated virtual target disk;
2. UEFI boot with the Tumbleweed systemd-boot/BLS path;
3. LUKS2 passphrase plus virtual TPM-backed primary unlock if VirtualBox exposes
   the required TPM behavior;
4. Btrfs/Snapper snapshot and rollback semantics;
5. transactional `dup` success and failure behavior;
6. soft reboot into the updated snapshot;
7. kexec remains disabled;
8. sensitive workload target remains blocked until maintenance success;
9. recovery/admin access remains available after forced maintenance failure;
10. no installer dependency on a second "host" disk.

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

1. Prove the architecture in VirtualBox.
2. Produce the Agama unattended profile from the validated VM configuration.
3. Implement only the minimal systemd maintenance gate required to bind
   transactional-update to the sensitive workload target.
4. Validate the same artifacts on the physical removable SSD/FA401EA.
5. Validate the real browser + external authorization device.
6. Treat the architecture as production-ready only after the physical checks
   above pass.
