# LinuxDev — lifecycle, snapshots, updates and boot security

**Selected architecture, 2026-10-17.** Design authority for LinuxDev
issue #17, not a claim of qualified deployment on the physical ASUS.
Use alongside [FINAL_DESIGN.md](FINAL_DESIGN.md) and
[RAID_INSTALL_FA401EA.md](RAID_INSTALL_FA401EA.md).
Unlike `portable/`, this system does **not** require its TPM+PIN,
transactional-update, custom UKI or remote-boot attestation stack.

## Fundamental contract

**System rollback must never silently rewind work.** Ubuntu root,
independent boot binaries, Factory QEMU supervisor, Ephemerd, each of
N existing Windows-registered WSL2 `ext4.vhdx` images and separate
Factory Btrfs/data VHDX are separate lifecycle/recovery scopes.
Windows boot, recovery partitions, TPM/BitLocker protectors and
existing RAID array metadata are not LinuxDev snapshot targets.

## Selected LinuxDev on-disk design

All partitions below are on **one NEW positively identified Linux
AMD RAIDXpert2 virtual LUN**, never on raw SSD2, WinOps Array 2 or
WinHome SSD1. Layout dimensions are design sizes, subject to LUN capacity.

| Location | Contents | Recovery |
| --- | --- | --- |
| 2 GiB Linux-only ESP, FAT32 | Ubuntu signed shim/GRUB/EFI, no Microsoft boot files | Verified signed rescue media; independent ESP backup |
| 4 GiB Linux-only /boot, ext4 | GRUB files, TWO or more matched kernel/initramfs generations including last-known-good | Versioned retained boot generation plus independent /boot backup |
| Remaining Linux LUN: LUKS2 passphrase | Root offline confidentiality; no TPM/PCR auto-unlock | Off-device LUKS recovery passphrase/header backup |
| LUKS2 -> single-device Btrfs `@system` | / including /etc, /usr, /var/lib/dpkg, signed DKMS config/source, kernel modules and service definitions | Snapper pre/post-update system snapshots |
| Btrfs `@home`, `@logs`, `@cache` | Operator home, logs, caches | Retained independently of @system rollback |
| Btrfs `@snapshots` | Snapper snapshot catalog | Separate from root snapshot tree; retention cleanup |
| Btrfs `@swap` | NOCOW file created with `btrfs filesystem mkswapfile`, host zswap + real NVMe swap | Excluded from any snapshot; suspend-to-disk/hibernate disabled |
| Btrfs `@factory-system` | Host side of Factory manager, authorized session-QEMU definitions, small supervisor qcow2 and guest config | Independent Factory-owned supervisor-only snapshot and external backup |
| Separate shared NTFS carrier | ORIGINAL per-WSL ext4.vhdx and companion Btrfs/AI data images | Never in host or whole-VM snapshot; independent per-distro backup |

The **ubuntu-desktop** package provides GNOME, but stock Ubuntu Desktop
guided storage does not provide this explicit LUKS+Btrfs subvolume+ESP
layout. Selected installation composition: **Ubuntu 26.04 LTS
Subiquity/curtin custom storage** with pinned verified AMD `rcraid`
for the chosen Linux LUN, then official `ubuntu-desktop` GNOME
packages. This remains a standard Ubuntu system, not a new distro.
The installer layout and full GNOME payload must be staged/tested
with a real isolated install first, not improvised on SSD2.

The unencrypted /boot is chosen for straightforward GRUB+LUKS2
booting and independent recovery; it does **not** protect the
Ubuntu initramfs against physical modification. No root TPM
automatic-unlock or "Linux crypto workstation" claim.

### Snapper rollback must actually boot

Ubuntu's familiar `subvol=@` fstab or `rootflags=subvol=@`
can defeat `snapper rollback`, which switches Btrfs's default
subvolume. **Build a default-subvolume-respecting root from the
beginning** (stable distinct subvolumes mounted by name, but no
stale explicit `subvol=@system` for /). Make `snapper` the
single snapshot manager and exercise create -> update -> rollback
-> power cycle on a disposable installation.

`/boot` is separate and **not atomically rolled back** with Btrfs.
Keep known-good old kernel and its matching initramfs in /boot
until all corresponding Snapper recovery points are retired.
Record (Snapper point, kernel exact version, initramfs SHA256,
DKMS rcraid module build/signer, boot validation).
On rollback select a retained kernel compatible with old root
and containing a working signed `rcraid`. An otherwise correct
snapshot with a broken/new unmatched initramfs is NOT a
successful rollback.

## Everyday update path — stock Ubuntu products

- Ubuntu 26.04 LTS release, security/updates pockets; stock
  APT and `unattended-upgrades` perform ordinary security
  package updates. GNOME shows pending updates/reboot.
  No forced automatic reboot, no custom parallel updater and
  no hard login denial that also blocks emergency recovery.
- Host **kernel, initramfs, bootloader and boot-critical rcraid
  DKMS** are one coordinated maintenance class: do not
  automatically activate unqualified new kernels/reboot.
  Process pending kernel security updates promptly in planned
  maintenance; no indefinite freeze of security patches.
- Begin each kernel transaction with a labeled **Snapper
  pre-update root snapshot + retained previous working kernel/
  initramfs**. Native APT/DKMS installs new kernel + matching
  headers, rebuilds and signs the pinned AMD module with MOK,
  includes it in that exact kernel's initramfs, and checks
  module signature, signer and initramfs contents. EFI mount,
  ESP ownership, GRUB menu and all old boot files are checked
  before allowing a controlled reboot.
- First boot of new generation must really load the intended
  RAID LUN via `rcraid`, mount the intended Btrfs root,
  reach GNOME/ROCm, restart Factory manager and preserve
  network. Only then label that pair **known-good** and
  permit pruning older boot files/snapshots according to
  retention policy. Never claim `dkms status` alone proves boot.
- Normal APT updates of package/userland also receive
  Snapper labeled pre/post snapshot points. Declarative
  APT hooks may invoke the STOCK Snapper tool; no second
  snapshot updater like Timeshift/apt-btrfs-snapshot and
  no home-grown transaction engine.
- Kernel/RAID/firmware updates must not be grouped with
  speculative Windows UEFI/BitLocker changes.
- Disable Linux hibernation: the shared NTFS/VHDX ownership
  must be cleanly relinquished between OS switches. Sleep
  for ordinary local sessions is a separately tested lifecycle.
  Disable Windows Fast Startup on Windows systems that own
  the shared writable NTFS carrier before Linux writes it.

## Three kinds of rollback (do not mix them)

### A. Ubuntu host root and boot failure

**System rollback** = Snapper Btrfs @system point +
**explicit matching retained /boot kernel/initramfs/rcraid**.
Remain logged in or boot with the previous GRUB kernel entry,
stop Factory manager, switch Btrfs root via Snapper, select
the compatible retained boot pair, reboot and verify actual
root, kernel and driver. @home, Factory QEMU, all WSL VHDXs
and AI data remain at their newest states.

**Won't boot at all:** use independent signed Ubuntu live/rescue
media with the matching, signed `rcraid` and tools staged
offline, open only LinuxDev LUKS2, recover Snapper root and
the *Linux-only* /boot/ESP. Do not repair by changing BIOS
RAID mode, clearing NVMe, replacing WinOps EFI or touching
WinHome disk. Damaged disk/RAID metadata is outside
Snapper recovery and needs external backup.

### B. Factory QEMU supervisor and Ephemerd

Factory owns one session-libvirt QEMU guest controlled from
its bounded host-side nspawn. Guest OS supervisor has its
own small `qcow2`. **Only that supervisor disk and separate
Ephemerd service configuration/state can be reverted.**
Take a **powered-off, explicitly disk-selective snapshot**
or an independent qcow2 copy with all WSL/data images marked
`snapshot=no`, and no guest-RAM save state. Factory can
repair and restart Ephemerd with guest systemd even when
CI/Ephemerd are stopped; candidate jobs cannot access
QEMU manager privileges.

Never create an external QCOW2 overlay on any original
WSL `ext4.vhdx`: QEMU would write to an overlay while
Windows later sees the **unchanged base image**, violating
the one-canonical-mutable-image rule. A whole-VM revert
that includes attached WSL data images is FORBIDDEN.
Transient overlays are permitted for disposable **test
copies**, not canonical WSL roots.

### C. Independently persisted WSL distro and shared AI data

Every WSL distro retains its original Windows registration,
root `ext4.vhdx`, UID/GID, package state and associated
Btrfs/data VHDX. ext4 has no native Btrfs snapshot semantics.
Back up each fully **stopped and unmounted** distro's file tree
incrementally using **restic** (including metadata) and retain
a verified **external full-image/VHDX backup** for byte-exact
recovery. Existing Windows Veeam/image backups can supply
the latter only when WSL VSS/shutdown consistency and actual
image coverage are proven; do not pretend a live open VHDX
is an automatically consistent snapshot.

Restore only the specifically requested broken distro.
WSL-A upgrade/rollback must not change WSL-B or any guest
supervisor/host root. Changes made on Windows and native
Linux always round-trip to the same original VHDX with
exclusive writer, clean guest stop, mount/flush/close and
Windows WSL termination. Ordinary host rollback must
never change the WSL image's path, identity or contents.

**Off-device recovery:** Snapper points and qcow2 snapshot
chains on SSD2 do NOT protect against SSD failure, BitLocker
carrier corruption or destructive RAID metadata changes.
Off-device restic repository and independent VHDX/full boot
backups are mandatory prior to a production Linux rollout.
Do not invent a backup target or assert the current Veeam
jobs already contain the necessary images; audit coverage
and prove a representative restore.

## Secure Boot: why preserve it on a *dev* OS?

**Decision: firmware Secure Boot stays ON for the entire ASUS.**
LinuxDev is development infrastructure, so do NOT impose
`portable/`'s high-assurance UKI/TPM2+PIN policy, but
there are two separate, working BitLocker TPM+PIN Windows
installations whose firmware policy and PCR7 measurements
can change if Secure Boot is disabled. It is irrational
to disturb both Windows for the convenience of bypassing
Ubuntu's native DKMS module signing.

Use Canonical-signed `shim`, GRUB and kernel; build/sign the
modified OEM AMD RAID DKMS module with Ubuntu's MOK machinery
and enroll a **module-signing-only** MOK. No self-owned firmware
PK/KEK/db replacement, no shim validation disable, no BIOS
Secure Boot toggling, no automatic TPM2-LUKS enrollment.
Save BitLocker recovery material **off laptop**; verify BOTH
Windows still unlock after initial MOK enrollment and future
firmware updates rather than promising zero PCR side effects.

**Security limit is explicit:** stock Ubuntu GRUB does NOT
authenticate initramfs; MOK private key commonly exists
root-owned on Linux filesystem, so compromise of host
root can sign hostile modules. LUKS passphrase protects
offline data, but unauthenticated /boot creates an
evil-maid passphrase theft exposure. This dev system
accepts that tradeoff, unlike the dedicated portable
crypto workstation. Secure Boot is retained primarily
for interoperability, baseline kernel signature
enforcement and BitLocker continuity, not claimed
to create full measured boot.

## Qualification / required real fault tests

| Failure case | Acceptance |
| --- | --- |
| Broken APT userspace update | Snapper root rollback boots, home and WSL data unchanged |
| Candidate kernel lacks usable signed `rcraid` | Old GRUB kernel + matching initramfs boots the real RAID root |
| Stale `rootflags=subvol=@system` | Detect during test; Snapper rollback MUST change actual boot root |
| Corrupt guest supervisor update | Factory restores ONLY qcow2 supervisor; each original WSL VHDX unchanged |
| Broken WSL-A userspace | Recover WSL-A independently; Windows still recognizes its original registration |
| Offline disk damage / stolen laptop | LUKS confidentiality and proven off-SSD restore material |
| MOK enrollment / changed boot state | Both Windows TPM+PIN boots usable or recoverable off-laptop |
| Kernel update under RAM pressure | Host zswap/NVMe swap works; no false guest RAM reservation |

## Sources

- https://documentation.ubuntu.com/security/security-features/platform-protections/secure-boot/
- https://learn.microsoft.com/en-us/troubleshoot/windows-client/windows-security/bitlocker-recovery-known-issues
- https://packages.ubuntu.com/resolute/snapper
- https://snapper.io/2014/04/29/rollback.html
- https://help.ubuntu.com/community/btrfs
- https://btrfs.readthedocs.io/en/latest/Swapfile.html
- https://ubuntu.com/server/docs/how-to/software/automatic-updates
- https://ubuntu.com/desktop/docs/en/26.04/reference/advanced-disk-setup-features/
- https://github.com/canonical/subiquity/blob/main/doc/howto/configure-storage.rst
- https://www.libvirt.org/kbase/backing_chains.html
