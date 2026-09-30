# Portable isolated workstation

## Status

Architecture baseline and declarative Ubuntu Autoinstall profiles for a Linux
workstation that runs from removable media and remains independent of the
host's installed operating systems.

The implementation rule is deliberately strict:

> Prefer distribution-supported declarative configuration. Do not add custom
> installer or runtime code merely to reproduce behavior already supported by
> Subiquity, Curtin, systemd, cloud-init, or package configuration.

## Goals

- Boot and operate from removable storage.
- Leave the host's internal disks, EFI System Partition, UEFI NVRAM, and boot
  order unchanged.
- Encrypt persistent non-boot state.
- Keep operating-system state separate from persistent user/application state.
- Support a fresh install and a reinstall that preserves persistent data.
- Patch the complete managed software surface before normal use.
- Provide a rollback point before system mutation.
- Keep installation reproducible and fail closed on layout mismatches.
- Minimize locally maintained code and special boot/storage machinery.

## Boot model

The device must boot through the UEFI removable-media fallback path and must
not rely on a persistent firmware boot entry.

Normal use:

```text
device absent
    -> host boots normally

device present + explicitly selected from the firmware one-time boot menu
    -> portable Linux boots
```

Hard invariants:

- Never create or modify a persistent UEFI boot entry.
- Never modify `BootOrder` or `BootNext`.
- Never write to an internal-disk ESP.
- Never depend on an internal bootloader.
- Internal disks are not part of the installation target.

The installer sets both Curtin and GRUB package configuration to avoid NVRAM
updates and to maintain the standard EFI removable-media fallback path.

## Declarative storage decision

The original design used Btrfs subvolumes to define the rollback and persistent
state boundaries. Stock Subiquity/Curtin cannot configure Btrfs subvolumes.

Rather than introduce a custom partitioner/subvolume script, the implementation
uses storage objects that Curtin supports declaratively:

```text
GPT
├── p1  EFI System Partition, FAT32, 1 GiB
│       /boot/efi
│
├── p2  boot filesystem, ext4, 2 GiB
│       /boot
│
└── p3  LUKS2
        └── LVM volume group: portable-vg
            ├── root     32 GiB  -> /
            ├── home      8 GiB  -> /home
            ├── persist  32 GiB  -> /persist
            ├── logs      4 GiB  -> /var/log
            └── free space        reserved for snapshots/growth
```

This is the first concrete reason for LVM in this design: it lets the installer
describe independent preserve/reformat boundaries without any helper code, and
it leaves free extents that can later back root snapshots.

The exact LV sizes are policy values, not architectural constants. They may be
adjusted before first provisioning, but fresh and reinstall profiles must stay
identical afterwards.

### Why /boot is separate and unencrypted

The Ubuntu Secure Boot path uses the distribution-signed GRUB. Ubuntu's signed
GRUB does not provide the LUKS2 pre-boot path required to read an encrypted
`/boot`. Keeping `/boot` separate therefore preserves the supported Secure
Boot chain without maintaining a custom bootloader.

This protects data at rest but does not claim protection against an attacker
who can modify an unattended removable device and later capture the disk
passphrase through a tampered initramfs. A future UKI-based design may address
that threat if required, but it must not be bolted onto this profile with
ad-hoc boot scripts.

## State boundaries

### root

The `root` LV contains executable and operating-system state:

- system packages and libraries;
- browser and application binaries;
- package databases;
- system configuration;
- system services.

It is the only filesystem reformatted by the reinstall profile.

### home

The `home` LV contains ordinary user-owned state and is preserved across
reinstall.

### persist

`/persist` is the explicit location for application profiles and persistent
application databases that should survive an OS reinstall.

### logs

`/var/log` survives an OS reinstall so evidence from a failed system remains
available for diagnosis.

## Installation profiles

There are deliberately two storage declarations instead of installer-side
branching code.

### `autoinstall-fresh.yaml`

Destructive initial provisioning:

- matches one exact target disk serial;
- creates GPT and all partitions;
- creates LUKS2 and the LVM volume group;
- creates and formats all LVs;
- installs Ubuntu Desktop minimal;
- installs updates before shutdown;
- configures US keyboard and `en_US.UTF-8`;
- configures zram and disables hibernation;
- powers off when complete.

### `autoinstall-reinstall.yaml`

Non-destructive reinstall of system state:

- requires the same exact disk serial;
- uses Curtin `preserve: true` checks for the disk, partitions, LUKS mapping,
  volume group, persistent LVs, and persistent filesystems;
- recreates the ESP and `/boot` filesystems;
- reformats only the `root` LV;
- preserves `home`, `persist`, and `logs`;
- aborts if the existing storage topology does not match the declaration.

No installer helper script chooses between these modes. The operator chooses
which YAML profile to boot with.

## Secrets and target identity

The repository is public. Therefore the profiles contain placeholders:

```text
__TARGET_DISK_SERIAL__
__LUKS_PASSPHRASE__
__PASSWORD_HASH__
```

A local installation copy must replace them before use. Secrets must never be
committed.

Using the exact disk serial is intentional. An unattended destructive install
must never choose "first USB disk", "largest disk", or any similarly ambiguous
match rule.

## Snapshots and rollback

Snapshots remain a requirement, but their implementation must follow the same
declarative-first rule.

With the LVM implementation, only the root LV needs automatic pre-update
snapshots; persistent LVs are outside system rollback. Free VG extents are
reserved for this purpose.

No custom snapshot/update shell state machine is currently part of the
repository. Before adding one, prefer a native package-manager/systemd/LVM
mechanism that can express:

```text
pre-update root snapshot
        ↓
update all managed executable state
        ↓
discard stale userspace
        ↓
validate
        ↓
allow interactive session
```

A failed or incompatible system state must never trigger automatic rollback of
`home`, `persist`, or `logs`.

## Mandatory boot-time update gate

The architecture still requires normal interactive work to be gated on an
update pass after boot.

Desired behavior:

```text
manual UEFI boot
        ↓
unlock LUKS
        ↓
maintenance/update phase
        ↓
pre-update root snapshot
        ↓
apply all managed updates
        ↓
reinitialize changed execution state
        ↓
validate
        ↓
normal interactive session
```

For userspace-only updates, a systemd soft reboot is preferred. Kernel or
microcode transitions require a stronger reinitialization. A true cold restart
must power off and require manual selection of the removable device again; it
must never manipulate firmware boot state.

The first scripted prototype for this gate was intentionally removed. Runtime
implementation will be added only when it can be expressed with a small,
auditable set of native declarative mechanisms instead of a bespoke state
machine.

## Reinstall and recovery semantics

The reinstall profile deliberately does not invent a storage migration.

If the declared topology matches:

```text
root      -> reformatted
home      -> preserved
persist   -> preserved
logs      -> preserved
LUKS      -> preserved
VG/LVs    -> preserved
partitions-> preserved
ESP/boot  -> rebuilt
```

If it does not match, installation stops. Drift is repaired deliberately,
rather than guessed by installation code.

## Security and simplicity principles

- Removability is an architectural boundary.
- The host firmware boot configuration is outside this system's authority.
- Exact device identity beats heuristic disk selection.
- Prefer declarative package/storage configuration to helper scripts.
- Minimize independent patch surfaces.
- Patch before normal use.
- Snapshot system state before mutation.
- Persistent data is never part of automatic system rollback.
- Fail closed when storage, boot, update, or validation invariants cannot be
  established.
