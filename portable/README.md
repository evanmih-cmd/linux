# Portable isolated workstation

## Status

This document is the **normative architecture** for the portable workstation.

Implementation artifacts must conform to this document. Installer limitations are
not a reason to silently change the architecture.

> **Implementation warning**
>
> The current `autoinstall-fresh.yaml` and `autoinstall-reinstall.yaml` files
> are obsolete LVM/ext4 experiments. They do **not** conform to this architecture
> and must not be used as installation profiles. They remain only until they are
> replaced by conforming declarative profiles.

The implementation preference is strict:

> Use distribution-supported declarative mechanisms wherever possible. Avoid
> bespoke installer/runtime code. If a chosen installer cannot express this
> architecture declaratively, change the provisioning mechanism rather than
> changing the architecture to fit the installer.

## Accepted decisions

The following are accepted architecture, not open design questions:

- Ubuntu 26.04 LTS, **Desktop Minimal**.
- US keyboard and `en_US.UTF-8`.
- Entire installation lives on removable media.
- The host's internal disks and firmware boot configuration are outside the
  authority of this system.
- UEFI Secure Boot remains enabled.
- The boot chain must provide **cryptographic integrity up to the point where
  LUKS is unlocked**.
- Boot integrity is provided with a **signed Unified Kernel Image (UKI)**.
- Only the EFI System Partition is unencrypted.
- Persistent system storage is **LUKS2 -> Btrfs**.
- Btrfs subvolumes define rollback and persistence boundaries.
- No LVM layer.
- No ZFS.
- Normal interactive use is blocked until the mandatory boot-time update gate
  completes successfully.
- All managed executable software belongs to one update domain.
- Every managed system update gets a rollback point first.
- System rollback never automatically rolls back persistent user/application
  state.
- A true cold restart must never be implemented by changing `BootOrder`,
  `BootNext`, or any other persistent host firmware setting.

## Goals

- Boot and operate entirely from removable storage.
- Leave internal storage, internal ESPs, UEFI NVRAM, and host boot order
  unchanged.
- Protect data at rest with LUKS2.
- Protect the pre-unlock boot path from unauthorized modification.
- Minimize patch latency by patching before normal use.
- Keep the executable system as one coherent rollback domain.
- Keep browser/application/user state outside automatic OS rollback.
- Make system rollback fast and deterministic.
- Support both fresh provisioning and reinstall while preserving persistent
  data.
- Make provisioning reproducible and as declarative as practical.
- Fail closed when boot, storage, update, or validation invariants cannot be
  established.

## Non-goals

- Sharing the host's internal bootloader or EFI System Partition.
- Creating a persistent UEFI boot entry for the removable device.
- Modifying `BootOrder` or `BootNext`.
- Maintaining separate update lifecycles for the browser, system, and other
  managed applications.
- Using filesystem snapshots as a substitute for backups.
- Automatically rolling persistent user/application data backward with the OS.
- Introducing LVM only to work around limitations of a particular installer.
- Maintaining a custom GRUB build merely to unlock LUKS2 before boot.

## Boot model

The removable device is self-contained.

When absent:

```text
host firmware
    -> host's normal boot path
```

When present and explicitly selected through the firmware one-time boot menu:

```text
host firmware
    -> removable ESP
    -> authenticated boot component
    -> signed UKI
    -> UKI-contained kernel + initrd + command line
    -> LUKS2 unlock
    -> encrypted system
```

The standard removable-media fallback path is used:

```text
EFI/
└── BOOT/
    └── BOOTX64.EFI
```

No permanent firmware entry is required.

### Hard firmware/host invariants

The portable system and its installer must never:

- create or modify a persistent UEFI boot entry;
- modify `BootOrder`;
- modify `BootNext`;
- write boot files to an internal-disk ESP;
- depend on the host's Windows/Linux bootloader;
- treat an internal disk as part of the portable storage graph.

The removable device must remain independently bootable after being moved to a
compatible machine whose Secure Boot trust configuration accepts its boot
chain.

## Pre-unlock boot integrity

The integrity boundary is explicit:

> Every executable/configuration artifact that can influence execution before
> LUKS unlock must be authenticated by the Secure Boot trust chain.

The UKI is the authoritative boot payload. It includes at least:

- Linux kernel;
- initrd;
- kernel command line required to reach the encrypted root.

There must not be a separate unsigned initrd on the unencrypted ESP that is
trusted merely because it is stored next to a signed bootloader.

The ESP is **not confidential**. Its security property is integrity through
signature verification.

The exact trust-enrollment mechanism (for example, which key ultimately signs
the UKI and how that key is enrolled) is an implementation decision, but it
must preserve the invariant above.

### No plaintext /boot requirement

There is no architectural requirement for a separate unencrypted `/boot`
filesystem.

Boot-critical artifacts required before LUKS unlock are exported to the ESP as
signed UKIs. Any ordinary `/boot` directory used by the installed system may
live inside the encrypted root.

This replaces the earlier GRUB/LUKS2 conflict without weakening the accepted
storage model.

## Storage layout

Normative layout:

```text
GPT
├── p1  EFI System Partition, FAT32, ~1 GiB
│       /efi
│       signed boot components + signed UKI(s)
│
└── p2  LUKS2
        └── Btrfs
            ├── @root       -> /
            ├── @home       -> /home
            ├── @appdata    -> /persist
            ├── @logs       -> /var/log
            └── @snapshots  -> /.snapshots
```

All Btrfs subvolumes share one free-space pool.

There are no fixed-size partitions for root/home/application state inside the
encrypted volume.

Suggested Btrfs mount policy:

```text
compress=zstd:1,noatime
```

Do not enable discard/TRIM by assumption. Enable periodic discard only after
the actual removable storage path is verified to propagate discard safely.

## Why no LVM

LVM was considered and rejected for the accepted architecture.

Btrfs already provides:

- shared free space across system and persistent state;
- copy-on-write snapshots;
- fast snapshot-based rollback;
- subvolume rollback boundaries;
- online growth and filesystem-aware resizing.

LVM would add another storage and recovery layer without solving a requirement
that Btrfs does not already solve here.

A provisioning tool's inability to create Btrfs subvolumes declaratively is an
implementation-tool limitation, not a reason to introduce LVM.

## Why Btrfs

Btrfs is used because rollback is a first-class requirement.

It provides:

- near-instant read-only snapshots;
- cheap writable snapshot clones for rollback;
- explicit subvolume boundaries;
- checksums;
- transparent compression;
- a single shared free-space pool.

The system is designed around these semantics.

## State boundaries

### `@root`: executable/system rollback domain

`@root` contains the complete coherent system state that must roll back
together, including:

- system executables and libraries;
- kernel-related state stored inside the encrypted system;
- package-manager databases and metadata;
- system configuration;
- system services;
- browser binaries;
- installed managed application binaries;
- package caches unless a concrete reason later requires separation.

The package database must always roll back with the binaries it describes.

There is deliberately **one executable update domain**.

### `@home`: ordinary user state

`@home` survives system rollback and reinstall.

It contains normal user-owned state that does not belong in the explicit
application persistence area.

### `@appdata`: explicit persistent application state

Mounted at:

```text
/persist
```

Expected structure may include:

```text
/persist/
├── browser/
├── applications/
└── state/
```

Use explicit profile/data locations where practical.

This state is never part of automatic root rollback.

A rare profile/schema incompatibility after emergency rollback is accepted as a
smaller risk than maintaining a second executable update cadence.

### `@logs`: diagnostic history

Mounted at `/var/log`.

Logs remain outside root rollback so that evidence from a failed update is
still available after the system is restored.

### `@snapshots`: rollback storage

Mounted at `/.snapshots`.

Snapshots are stored outside `@root` so that a root snapshot does not
recursively snapshot snapshot storage.

## Ephemeral state

Use volatile storage where persistence provides no value:

```text
/tmp      -> tmpfs
swap      -> zram only
hibernate -> disabled
```

No disk-backed swap is part of the design.

## Snapshot policy

Before every managed update of executable/system state, create a read-only
snapshot of `@root`.

Typical retained states:

```text
factory-good
last-known-good
pre-update-1
pre-update-2
pre-update-3
pre-update-4
```

Rules:

- `factory-good` is never removed automatically.
- `last-known-good` is replaced only after successful post-update validation.
- pre-update snapshots are pruned only after the new state is validated.
- update must not begin if its rollback point cannot be created.
- persistent subvolumes are not snapshotted as part of the system transaction.

Snapshots are rollback points, not backups.

## ESP handling

The ESP is normally treated as immutable runtime state.

Normal policy:

- mount the ESP read-only outside controlled boot-artifact updates;
- before changing UKIs or other boot files, store a copy of the current ESP
  contents inside encrypted rollback storage associated with the same
  transaction;
- remount the ESP read-write only for the controlled update;
- write the new signed boot artifacts;
- return the ESP to read-only state.

If a rollback crosses an update that changed boot artifacts, restore the
matching root snapshot and the matching ESP backup as one transaction.

## Mandatory boot-time update gate

Normal interactive work is not allowed immediately after boot.

Every boot enters a maintenance/update phase first:

```text
manual UEFI selection of removable device
        ↓
authenticated UKI boot
        ↓
LUKS2 unlock
        ↓
encrypted system mounted
        ↓
network ready
        ↓
create read-only @root snapshot
        ↓
refresh trusted software metadata
        ↓
apply ALL managed updates
        ↓
reinitialize execution state
        ↓
post-update validation
        ↓
mark state last-known-good
        ↓
allow graphical session
```

This is a **mandatory gate**, not a best-effort background update.

A graphical/login session must remain unavailable while the gate is incomplete
or failed.

### Update scope

The update pass covers the complete managed executable surface, not only
packages labelled "security".

That includes the operating system and all managed applications used by the
workstation.

Software that cannot be brought under this single managed update lifecycle is
disfavored.

## Reinitialization after updates

The design does not rely on selectively guessing which processes need restart.

After executable state changes, stale execution state is discarded before the
user is allowed to work.

### Userspace-only update

Use a systemd soft reboot:

```text
updated filesystem
    ↓
systemctl soft-reboot
    ↓
fresh userspace
    ↓
validation
    ↓
interactive session
```

This ensures that processes using superseded executable/library inodes do not
survive into the working session.

### Kernel/initrd/UKI update

When a new kernel execution state is required, prefer a trusted
Secure-Boot-compatible `kexec` transition that loads the new kernel/initrd
from the already authenticated and unlocked system context.

The exact implementation must preserve platform lockdown/signature
requirements.

If a safe trusted `kexec` transition cannot be established, fail over to the
cold-restart path below rather than weakening verification.

### True cold restart

Some transitions may genuinely require firmware re-entry.

In that case:

1. do not allow an interactive session;
2. show a clear maintenance message;
3. power the machine off;
4. require the user to power on and manually select the removable device again
   from the one-time boot menu.

Never use `BootNext`, `BootOrder`, or another host firmware mutation to make
this path more convenient.

## Rollback model

Do not depend on changing the Btrfs default subvolume.

The booted system always targets the canonical subvolume name:

```text
@root
```

Rollback works by replacing the object behind that stable name:

```text
@root
    -> @root.failed-<timestamp>

selected read-only snapshot
    -> writable clone named @root
```

Then reinitialize/reboot as required.

Keep the failed root temporarily for diagnosis. Delete it only after the
restored system is validated.

Persistent subvolumes remain untouched.

## Recovery model

The installation medium is also the recovery environment.

When the installed system cannot boot normally:

```text
boot installer/recovery medium
        ↓
unlock target LUKS2
        ↓
mount Btrfs top level
        ↓
select root snapshot
        ↓
restore canonical @root
        ↓
restore matching ESP backup if required
        ↓
power off
        ↓
manually boot the removable workstation again
```

Recovery must not require modifying host firmware state or an internal disk.

## Provisioning model

There are two accepted provisioning operations.

### Fresh install

Destructive initial provisioning:

1. select/identify the exact removable target;
2. create GPT;
3. create standalone ESP;
4. create LUKS2 container;
5. create Btrfs;
6. create required subvolumes;
7. install Ubuntu 26.04 LTS Desktop Minimal;
8. install/configure the authenticated UKI boot path;
9. configure mounts, zram, tmpfs, hibernation policy, update gate, snapshot
   policy, and recovery tooling;
10. fully update the new installation;
11. validate that host storage/NVRAM were not modified;
12. create `factory-good` and `last-known-good`;
13. power off.

### Reinstall preserving persistent state

Reinstall uses the same storage architecture and preserves:

- LUKS2 container;
- Btrfs filesystem;
- `@home`;
- `@appdata`;
- `@logs`;
- existing snapshot history unless explicitly pruned.

Before replacing the system root:

1. back up current ESP boot artifacts into encrypted snapshot storage;
2. replace/recreate only `@root`;
3. reinstall the OS into the canonical `@root`;
4. rebuild signed UKIs/boot artifacts;
5. fully update;
6. validate;
7. establish the new `last-known-good`.

Persistent data is not reformatted as part of reinstall.

## Declarative implementation requirement

Fresh and reinstall may be separate unattended profiles.

Interactive installer UI is not a priority.

The preferred implementation is:

```text
autoinstall-fresh
autoinstall-reinstall
```

with no custom interactive storage program.

However, the profiles must implement the architecture above.

If stock Subiquity/Curtin cannot declaratively express the required Btrfs
subvolume lifecycle, the correct response is to select another declarative
provisioning mechanism or image-building approach. The architecture must not be
changed to LVM/ext4 merely to fit Curtin's current storage model.

Custom imperative code is a last resort and requires an explicit architecture
decision before introduction.

## Idempotence

After destructive initial provisioning, repeated configuration/convergence must
be safe.

A conforming provisioning mechanism should:

- verify the expected partition/LUKS/Btrfs/subvolume topology;
- verify signed-UKI boot configuration;
- repair expected packages/configuration/services;
- preserve persistent subvolumes;
- preserve secrets/identities unless explicitly rotated;
- make no material changes when the system already matches the declaration.

It must not silently repartition or reformat persistent state during
convergence.

## Installer target safety

A destructive unattended profile must identify the target deterministically.

Exact serial/WWN matching is preferred when supported.

It must never use ambiguous rules such as:

- first USB disk;
- largest disk;
- first non-installer disk.

Target identity is an implementation safety control, not a reason to alter the
storage architecture.

## Security and simplicity principles

- Removability is an architectural boundary.
- Boot integrity extends through the UKI to the LUKS unlock point.
- The host's firmware boot configuration is outside this system's authority.
- Only the ESP is unencrypted.
- LUKS2 + Btrfs is the accepted storage model.
- Btrfs subvolumes define rollback/persistence boundaries.
- One executable update domain is simpler and safer than multiple patch
  lifecycles.
- Patch before use.
- Snapshot before mutation.
- Reinitialize after mutation.
- Persistent data is never part of automatic system rollback.
- Prefer recovery from known snapshots over complicated snapshot boot menus.
- Prefer declarative distribution mechanisms over bespoke code.
- Installer limitations do not redefine architecture.
- Fail closed when an invariant cannot be established.

## Open implementation decisions

The architecture is fixed; these implementation details are still open:

- exact Secure Boot trust-enrollment/key-management model for signing UKIs;
- exact UKI generation/update tooling on Ubuntu 26.04;
- exact declarative provisioning mechanism capable of creating and preserving
  the required Btrfs subvolumes without bespoke storage code;
- exact implementation of the mandatory update gate using native
  systemd/package-manager mechanisms;
- exact trusted `kexec` mechanism for kernel/initrd transitions;
- exact health checks performed before releasing the graphical session;
- exact snapshot retention thresholds once real storage consumption is known;
- whether verified USB discard support justifies periodic TRIM.

Any implementation choice must preserve the accepted invariants above.
