# RAIDXpert2 boot path for the ACTUAL ASUS FA401EA (evidence-to-install contract)

Status: **research completed to an identified driver/installer implementation path;
installation and compatibility on the physical ASUS NOT YET verified**.
Date 2026-10-17. Owner: LinuxDev issue #17.

## Exact target — do not substitute generic NVMe/RAID0 instructions

- Laptop: **ASUS TUF A14 FA401EA**, Ryzen AI Max+ 392 / Radeon 8060S,
  64 GB UMA, firmware RAID mode already in use.
- **SSD1**: original Windows Home; separate boot/recovery, not a Linux installation target.
- **SSD2**: Lexar NM790 4TB, AMD RAIDXpert2 logical volumes **carved from
  one physical NVMe**. WinOps Pro is already booting from **AMD-RAID
  Array 2** with its own 300 MiB ESP, 16 MiB MSR, NTFS C:, 2 GiB WinRE,
  BitLocker TPM+PIN.
- Windows installation used exact ASUS RAID driver path
  `rcbottom → rcraid → rccfg`. Loading only `rcraid` originally showed
  wrong raw-NVMe geometry. `Disk 1` in one Windows boot is NOT a
  durable device identity or Linux installation selector.
- Future LinuxDev occupies its **own AMD virtual LUN and independent ESP**,
  not the raw SSD2 NVMe device and not WinOps C:, Home ESP or WinRE.
  The final Linux LUN does NOT currently have verified physical identity,
  size, or completed boot from Ubuntu.
- Actual Windows evidence:
  https://github.com/evanmih-cmd/linux/issues/9#issuecomment-6110011694

## Actual source coverage — an existing mature RAID product, with an APU-specific defect

### Supported AMD semantics

AMD RAID User Guide **53987 Rev. 3.31 (April 2025)**, sec. 5.4,
describes **up to 12 arrays** and allows different portions of the same
disk to be assigned to different arrays. Sec. 5.8 documents:
`rcadm --create --volume` / `--raidable` on **one physical disk**.
Therefore one-NVMe-many-virtual-LUNs is intentional RAIDCore/RAIDXpert2
functionality, **not** an invalid or unsupported concept.

AMD Ubuntu RAID Quick Start Guide **56966 rev 1.01, March 2025**
documents official vendor Linux `rcraid` driver 9.3.2/9.3.3,
`driver_sdk`, pre/post-install and Secure Boot/MOK signing.
Official examples target older/workstation-class AMD platforms:
they do NOT establish vendor support for **Ubuntu 26.04 kernel 7.0
on FA401EA APU**.

Sources:
- https://docs.amd.com/api/khub/documents/l4s9wihuwBewawVYkF1dIQ/content
- https://docs.amd.com/api/khub/documents/l_VvImC0IX9mjsLPOPymFw/content

### Closest known executable APU driver path

**DesktopECHO/rcraid-nvme** was created Feb 2026 and uses original
AMD Linux proprietary RAID blob **9.3.3.302** from Lenovo's 2026 OEM
RAIDXpert2 RPM `raidxpert2-9.3.3_00302-1.x86_64.rpm`, plus
kernel-source and proprietary-blob patches:

1. Modern Linux kernel APIs from ~6.12 up through Linux 7.0.
2. Trapped NVMe PCI interface `1022:b000`: missing `NvmeTrapDeviceVar`
   on APU/SoC platforms; patch supplies VID/DID fallback so the AMD
   RAIDcore enumerates real NVMe behind the synthetic controller.
3. AMD RAIDCore's CPUID-based `RC_HW_OS_GetLicenseLevel` selects an APU
   sub-type with RAID features masked out. Binary patch corrects/overrides
   feature selection and additional `RC_CoreFeatureSet` filtering.
4. Supports `rcadm`, RAIDXpert2 GUI, DKMS and initramfs hooks. This
   keeps AMD's underlying Volume/RAIDABLE/multiple-array RAIDcore,
   unlike the community clean-room `joeytroy/amd-raid-driver` which
   has only experimentally demonstrated **RAID0/RAID1 on two
   Crucial T700** under TRX50.

Sources:
- https://github.com/DesktopECHO/rcraid-nvme
- https://github.com/DesktopECHO/rcraid-nvme/blob/main/raidxpert2-install
- Lenovo OEM AMD RAID 9.3.3.302:
  https://support.lenovo.com/bb/en/downloads/DS579640

**Evidence precision:**
- The DesktopECHO README's target says *Minisforum UM890 Pro / Ryzen
  9 8945HS / "Strix Halo"*. Ryzen 9 8945HS is **Hawk Point**, NOT
  Ryzen AI Max+ 392 / Strix Halo. Treat the label as an error;
  the specific user's ASUS FA401EA **has not been physically proven**
  by that example.
- An independent user in issue #4 initially reported successful
  Debian 13/RAID0 on ASUS TRX50 but **retracted immediate confidence
  after reboot**, reporting required manual driver reload and reduced
  IO. Do not count that as verified persistent boot on another board.
  https://github.com/DesktopECHO/rcraid-nvme/issues/4
- The main branch was updated **2026-07-23**, revision
  `7ef6506b1dc6427ea9a1eabff5c83dd84e10c3fc`, after a
  **March 6** published release tagged `1`; that release binary
  **predates** later stack-canary/thunk fixes. Do not use its old
  .deb as a proof of Linux 7.0 compatibility.
- AMD binary blob is modified: vendor **does not support** this
  unofficial build. Exact Linux 7.0 module signing, MOK,
  Security Boot and kernel-update discipline required.

## Important hazard found by reading actual install script — DO NOT EXECUTE UNMODIFIED

`raidxpert2-install` does more than compile an `rcraid.ko`:

- It self-elevates, downloads/installs packages, DKMS-builds, loads
  the RAID driver, regenerates initramfs, enters an automatic
  installer-wait/chroot procedure and eventually calls `reboot`.
  This is not a non-destructive read-only probe.
- **Lines 732–755**: Debian target installation is recognized only
  by Calamares path regex `/tmp/calamares-root-........`, or Fedora
  `/mnt/sysroot`. Stock **Ubuntu 26.04 Desktop** runs
  `ubuntu-desktop-bootstrap`/Subiquity, NOT this Calamares
  install mount contract. Therefore upstream's automation
  cannot be relied upon to identify its installed root.
- **Lines 763–797** select ESP using
  `blkid -t TYPE=vfat -o device | grep -v loop | head -1`.
  This can choose **WinHome ESP or WinOps ESP** instead of the new
  Linux LUN. Destructive boot coupling on this machine.
- **Lines 803–812** run `linux-headers-$(uname -r)` inside chroot;
  this resolves the currently running *live USB kernel*, not
  necessarily the newly installed target kernel. Driver can
  be absent from the first-boot target initramfs.
- The DKMS lifecycle code around lines 458–520 suppresses
  some initramfs failures with `|| true`, falls back to manually
  copying a failed DKMS installed module and ignores
  `modprobe` failure, permitting false success reports.

These are source-proven defects in *the script's suitability to
this installation*, not speculative bugs in every RAID driver.
No unmodified `raidxpert2-install`, no `install-livecd.sh`, no
auto-selected ESP, no `Erase disk and install`, no raw NVMe format,
no automatic fallback to host NVMe driver.

Sources:
- https://github.com/DesktopECHO/rcraid-nvme/blob/main/raidxpert2-install
- https://discourse.ubuntu.com/t/install-of-26-04-desktop-without-bootloader/82230
- https://lists.ubuntu.com/archives/technical-board/2025-May/003016.html

## Machine-specific install plan — selected integration, not an option list

**Driver source:** original AMD Linux 9.3.3.302 via OEM distribution,
adapted by a pinned, audited DesktopECHO **main Jul 23 commit**.
A minimal **LinuxDev-specific integration** shall separate
the driver build from its unsuitable auto-installer. It shall
use the official Ubuntu 26.04 LTS **Subiquity/curtin custom-storage**
installation primitives with explicit target LUN selection, followed by
stock Ubuntu **ubuntu-desktop** GNOME packages, and
separately provision target initramfs/ESP. This is a one-off
vendor-port adaptation, not a new generic RAID engine.

**Preparations on the installed Windows ASUS (read-only)**
1. From existing WinOps RAID utilities, retrieve actual
   physical NVMe/controller PCI ID, RAID array names, size, type,
   member and offset for all current LUNs. Correlate WinOps
   `AMD-RAID Array 2` GPT and its ESP/Windows/WinRE boundaries
   with RAIDCore `rcadm`/RAIDXpert2 records.
2. Confirm actual free/unallocated capacity on SSD2 RAID controller,
   not just a raw NVMe sector map; identify the operator-approved
   **new** Linux LUN by array identity and size. Windows Home
   must remain bootable and physically independent.
3. Secure independent offline backups of Windows/BitLocker recovery
   and physical return path. No RAID mode change. This is an
   acceptance prerequisite, not a Linux imaging workaround.

**Host filesystem/boot lifecycle selected in
[LIFECYCLE.md](LIFECYCLE.md):** one NEW Linux RAID LUN
gets a separate 2 GiB ESP and 4 GiB /boot;
LUKS2/Btrfs Snapper system root and independent
snapshot-excluded swap + home. Use Ubuntu 26.04
Subiquity/curtin custom storage, then official GNOME
packages; retain a last-known-good signed kernel/initramfs/
rcraid boot generation. Firmware Secure Boot stays ON;
MOK signs `rcraid`, no Windows EFI changes.

**Linux live media build/boot (offline-capable after staging)**
4. Prepare Ubuntu 26.04.1 **Server/Subiquity custom-storage** installation
   media with the staged official `ubuntu-desktop` GNOME packages and vendor RAID
   9.3.3.302+audited patch source, exact kernel headers/build
   packages and local binary signatures on the media *before*
   boot. Keep Secure Boot on; arrange module signing/MOK
   enrollment via documented DKMS mechanism, not a silent
   Secure-Boot-disable requirement.
5. In live session **before writing** read PCI controller
   identity and raw/detected block devices. Build patched
   `rcraid` module for **the exact live kernel** independently
   of upstream installer workflow. Load/reprobe cautiously
   only with already secured recovery and exact controller/SSD
   identity. On enumeration: verify **every already-existing
   RAID LUN**, GPT ESP of WinOps, logical capacity and
   RAID metadata match the Windows source; raw 4 TB Lexar
   NVMe is NEVER considered a candidate target. No writes
   or import/adoption of alien/degraded arrays.
6. If and only if the new intended Linux **RAID virtual disk**
   is separately identifiable and no Windows disks are
   misrecognized, carry out user-approved target-only
   partitioning: its **own 2 GiB ESP**, 4 GiB Linux-only /boot,
   and LUKS2+Btrfs root with Snapper-managed system and separate
   home/swap subvolumes. Ubuntu 26.04 Subiquity/curtin custom storage
   targets this **one identified LUN only**, then installs GNOME
   with official Ubuntu packages; other LUNs stay protected.
   User-selected target identity is explicit.
7. Install DKMS **and signed** `rcraid` for the TARGET Ubuntu
   kernel version (not necessarily live kernel), regenerate
   and independently inspect target initramfs module included
   and module-signature acceptance. Boot files/BCD/ESP must
   be exclusively on target Linux LUN. No first-found-FAT.
8. Verify cold boot, kernel upgrade/rebuild on a disposable
   alternative kernel then return, RAID LUN data integrity,
   no change to WinOps/WinHome independent boot, normal
   recovery. No "PASS" from module-load alone. Audit
   physical SSD2 RAID metadata and volumes after first
   Linux boot and Windows resume.

**User involvement:** selection of the new Linux virtual disk
in the installer is manual/intentional as in Windows, but
no repeated diagnostic commands or trial-and-error demanded
from the owner. Before live access, the agent can prepare
the static integration; on hardware, agent may collect
read-only information through existing authorized tools.
Current `SECUREWS` remote agent status is **offline**,
so no real ASUS proof has occurred during this research.

### Final accuracy / remaining genuine fact

Documented operation exists for single-disk RAIDABLE/Volume
and many LUNs; the APU-specific port exists and a third
party claims functioning Linux. But **no verified independent
end-to-end Ubuntu 26.04 boot on FA401EA, Max+ 392, one
Lexar NM790 with multiple LUNs** was obtained from sources
reviewed by 2026-10-17. The correct status is a defined,
implementable integration path with identifiable acceptance
gates — neither "no Linux driver" nor "already proven safe".
