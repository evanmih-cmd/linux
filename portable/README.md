# Portable isolated workstation

## Status

Architecture baseline for an idempotently provisioned Linux workstation that runs entirely from removable media and remains independent of the host machine's installed operating systems.

## Goals

- Boot and operate entirely from removable storage.
- Leave the host's internal storage, EFI System Partition, boot order, and UEFI NVRAM unchanged.
- Encrypt all persistent non-boot state.
- Keep system state separately rollbackable from user and application data.
- Patch the complete executable software surface before an interactive session is allowed.
- Make update rollback fast and deterministic.
- Keep installation and repair reproducible from a separate installer medium.
- Prefer simple, upstream-supported mechanisms over additional storage or boot layers.

## Non-goals

- Sharing a bootloader or EFI System Partition with an installed host OS.
- Creating persistent UEFI boot entries or modifying `BootOrder` / `BootNext`.
- Using LVM solely for space allocation between system and data.
- Using ZFS for a single-device root filesystem.
- Automatically rolling back user or application data with the operating system.
- Treating filesystem snapshots as backups.

## Boot model

The removable device is self-contained and uses the standard removable-media UEFI path:

```text
EFI/
└── BOOT/
    └── BOOTX64.EFI
```

Normal operation is:

```text
device absent
    -> host boots normally

device present + explicitly selected in the firmware one-time boot menu
    -> portable Linux boots
```

Hard invariants:

- Never create or modify persistent UEFI boot entries.
- Never modify `BootOrder` or `BootNext`.
- Never write boot files to an internal-disk ESP.
- Never depend on an internal bootloader.
- Internal disks are not automatically mounted.

Secure Boot remains enabled. The boot chain must use distribution-supported signed components.

## Storage layout

```text
GPT
├── p1  EFI System Partition, FAT32, 1 GiB
│       mounted at /efi
│
└── p2  LUKS2
        └── Btrfs
            ├── @root       -> /
            ├── @home       -> /home
            ├── @appdata    -> /persist
            ├── @logs       -> /var/log
            └── @snapshots  -> /.snapshots
```

### Why no LVM

Btrfs subvolumes share one free-space pool, so system and persistent data do not need fixed-size logical volumes. Btrfs can grow directly with its underlying encrypted partition. Adding LVM would add another recovery and provisioning layer without solving a current requirement.

### Why Btrfs

Btrfs provides:

- near-instant copy-on-write snapshots;
- subvolume boundaries that naturally define rollback domains;
- shared free space across system and persistent data;
- checksums;
- transparent compression;
- simple snapshot cloning for recovery.

Suggested mount policy:

```text
compress=zstd:1,noatime
```

Do not enable discard/TRIM merely by assumption. Enable periodic discard only after the actual removable device path is verified to propagate discard safely.

## State boundaries

### `@root`: executable and system state

Everything required for a coherent operating-system rollback remains in `@root`, including:

- kernel and initramfs material stored on the encrypted filesystem;
- system libraries and executables;
- system services;
- package-manager databases and metadata;
- browser binaries;
- installed application binaries;
- system configuration;
- system package caches unless a concrete reason emerges to separate them.

The package database must roll back with the binaries it describes.

There is deliberately only one executable update domain. Applications that are part of the workstation must participate in the same managed update transaction rather than creating an independent patch lifecycle.

### `@home`: ordinary user state

User-owned state that should survive a system rollback lives under `/home`.

Do not rely on `@home` as the only place for important application state when an application supports an explicit profile/data location.

### `@appdata`: persistent application state

Mounted at `/persist`.

Use explicit application profile/data paths where practical:

```text
/persist/
├── browser/
├── applications/
└── state/
```

Examples include browser profiles and application-specific persistent databases or configuration whose loss or rollback would be undesirable.

This state is intentionally not part of a system snapshot. A rare application-profile compatibility problem after an emergency system rollback is accepted as preferable to maintaining a second, slower patch surface. Such incompatibilities are repaired explicitly if they occur.

### `@logs`: persistent diagnostic history

`/var/log` remains outside the system rollback domain so that logs from a failed update survive a rollback and remain available for diagnosis.

### `@snapshots`: snapshot storage

Snapshots are stored separately so snapshots do not recursively snapshot themselves.

## Ephemeral state

Use volatile storage where persistence has no value:

```text
/tmp      -> tmpfs
swap      -> zram
hibernate -> disabled
```

There is no disk-backed swap by default.

## Snapshot policy

Before every managed mutation of executable/system state, create a read-only snapshot of `@root`.

A useful retention model is:

```text
factory-good        retained until deliberately replaced
last-known-good     most recently validated state
pre-update-1
pre-update-2
pre-update-3
pre-update-4
```

Old snapshots are pruned only after the new state has successfully passed its post-update validation.

Snapshot creation is part of the transaction. An update must not proceed if its rollback point cannot be created.

Snapshots are rollback points, not backups. Backup policy for persistent data is a separate concern.

## Mandatory boot-time update gate

An interactive user session is not allowed immediately after boot.

Every boot enters a maintenance gate first:

```text
manual UEFI boot of removable device
        ↓
LUKS unlock
        ↓
maintenance target
        ↓
network ready
        ↓
create read-only @root snapshot
        ↓
refresh trusted package/application metadata
        ↓
apply all managed updates
        ↓
reinitialize running software
        ↓
post-update validation
        ↓
mark state known-good
        ↓
allow interactive session
```

The objective is that a user never begins normal work in a newly booted environment while known managed updates remain unapplied.

The updater should patch the full managed software surface, not security-labelled packages only. Splitting normal and security updates creates avoidable divergence and leaves executable state on multiple cadences.

## Reinitialization after updates

After package application, no normal interactive session may reuse processes that were started against superseded executable/library inodes.

Use the strongest reinitialization necessary without unnecessarily returning through firmware.

### Userspace-only change

Perform a systemd soft reboot:

```text
patched root
    ↓
systemctl soft-reboot
    ↓
fresh userspace
    ↓
post-update validation
```

The kernel remains running, while userspace is rebuilt from the updated filesystem state.

### Kernel or initramfs change

Load the newly installed trusted kernel directly with the Secure-Boot-compatible kexec path:

```text
old kernel
    ↓
load new signed kernel + new initramfs
    ↓
kexec
    ↓
new kernel + fresh userspace
    ↓
post-update validation
```

A kernel transition must fail closed if the new kernel cannot be validated or loaded through the trusted path.

### Bootloader / removable ESP change

Updating the removable device's bootloader does not require restarting the current session merely to exercise the new bootloader. The new boot chain is exercised on the next manual firmware boot.

### Cold restart required

Some changes may genuinely require a complete firmware boot.

In that case:

1. do not permit the interactive session;
2. present a clear maintenance message;
3. power off rather than reboot;
4. require the user to manually select the removable device again from the one-time firmware boot menu.

Never work around this case by changing host UEFI boot state.

## EFI System Partition handling

The ESP is intentionally outside LUKS because UEFI must read it before the encrypted root can be unlocked.

Normal mount policy:

- mount the ESP read-only outside a controlled boot update;
- remount read-write only for a managed transaction that needs to change boot files;
- before changing it, copy its current contents into encrypted rollback storage associated with the same update transaction;
- remount it read-only after the transaction.

A rollback transaction that must revert the boot chain restores the matching ESP backup together with the root state.

## Rollback model

Do not depend on changing the Btrfs default subvolume at runtime.

The boot configuration always targets the canonical root subvolume name:

```text
subvol=@root
```

Rollback replaces the object behind that stable name:

```text
@root
    -> @root.failed-<timestamp>

selected read-only snapshot
    -> writable clone named @root
```

Then reinitialize or reboot as required.

Keep the failed root temporarily for diagnosis. Delete it only after the restored system is validated.

### Recovery when the installed system does not boot

The installer medium is also the recovery environment:

```text
boot installer/recovery medium
    ↓
unlock target LUKS container
    ↓
mount Btrfs top level
    ↓
select snapshot
    ↓
restore canonical @root
    ↓
restore matching ESP backup if required
    ↓
power off
    ↓
manually boot the removable workstation again
```

No host boot configuration is needed for recovery.

## Installer architecture

Provisioning is driven from a separate installer medium.

The installer must be idempotent after initial destructive provisioning: rerunning it against an already provisioned target converges configuration without repartitioning, regenerating identities, or destroying persistent state.

Separate two modes clearly:

### Initial provisioning

Destructive and explicit:

1. identify the target removable device by stable attributes and verify that it is not an internal disk;
2. create GPT;
3. create the standalone ESP;
4. create the encrypted partition;
5. initialize LUKS2;
6. create Btrfs and required subvolumes;
7. install the base system;
8. install the removable Secure Boot boot chain;
9. configure mounts, update gate, snapshot/rollback tooling, networking, and hardening;
10. validate that no internal disk or firmware boot state was modified;
11. create `factory-good`.

Initial provisioning must require explicit confirmation of the target device before destructive changes.

### Convergence / repair

Non-destructive by default:

- verify and repair expected packages;
- verify system configuration;
- verify subvolume and mount layout;
- verify boot files on the removable ESP;
- verify update/rollback services;
- repair permissions and service enablement;
- preserve `@home`, `@appdata`, `@logs`, and existing snapshots unless an explicit maintenance action says otherwise.

Repeated runs with no drift should make no material changes.

## Update transaction requirements

A single managed update entry point owns executable-state mutation.

Conceptually:

```text
portable-update

1. acquire exclusive maintenance lock
2. verify storage and snapshot prerequisites
3. create read-only root snapshot
4. back up ESP if the transaction may modify it
5. refresh trusted metadata
6. apply all managed updates
7. classify required reinitialization
8. perform soft reboot / trusted kexec / cold-poweroff gate as needed
9. run post-update validation in the new execution state
10. mark the state known-good
11. prune retention-exceeded snapshots
12. release the interactive-session gate
```

Manual package installation or ad-hoc application self-updaters should not bypass this transaction model.

## Validation

Before an interactive session is released, validate at minimum:

- root is mounted from the expected removable device and `@root`;
- encrypted storage is active;
- persistent subvolumes are mounted at their expected paths;
- the internal disks are not mounted by policy;
- the package manager reports no incomplete transaction;
- the managed update pass completed successfully;
- current kernel matches the required installed kernel when a kernel transition was required;
- critical services are healthy;
- ESP is read-only outside a boot update;
- no forbidden host UEFI/NVRAM mutation was performed.

Failures keep the system in maintenance/recovery mode rather than opening a normal session.

## Security and simplicity principles

- Removability is an architectural boundary, not merely an installation detail.
- The host machine's boot configuration is outside the system's authority.
- Minimize independent patch surfaces.
- Patch before use.
- Snapshot before mutation.
- Reinitialize after mutation.
- Keep persistent data outside automatic system rollback.
- Prefer recovery from a known snapshot over complicated boot-menu snapshot integration.
- Prefer upstream distribution mechanisms and a small number of explicit local orchestration components.
- Fail closed when update, validation, trusted kernel transition, or storage invariants cannot be established.

## Open implementation decisions

The architecture intentionally leaves these implementation choices for the build phase:

- exact Ubuntu LTS point release used as the base;
- bootloader details within the distribution-supported Secure Boot chain;
- exact trusted package sources for required applications;
- implementation language for installer/update/rollback orchestration;
- snapshot retention thresholds based on observed storage use;
- whether verified device discard support justifies periodic TRIM;
- exact post-update health checks for the final application set.

These choices must preserve the invariants above.
