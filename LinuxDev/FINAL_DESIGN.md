# LinuxDev — selected system architecture, 2026-10-17

**The selected architecture is ONE product topology. No either/or branches.**
It is an accepted technical design, **not** evidence of finished deployment
or validation on physical ASUS. Source requirements:
[BUSINESS_REQUIREMENTS.md](BUSINESS_REQUIREMENTS.md).

## Physical host

Ubuntu 26.04 LTS Desktop/GNOME on ASUS TUF A14 FA401EA,
Ryzen AI Max+ 392, Radeon 8060S, 64GB unified RAM. Native amdgpu/ROCm
and llama.cpp for direct GPU/UMA inference. Host owns hardware RAID,
boot/UEFI, device access, filesystem carrier unlock, the explicit Factory
exposed-disk catalog, network firewall, cgroup priorities and swap.

Original Windows 11 Home (SSD1), WinOps 11 Pro (AMD RAIDXpert2
SSD2 LUN), their BitLocker/boot/recovery and existing WSL2 VHDX
data remain unchanged until the planned rollout. **AMD has official
Linux RAID driver/product support**: vendor Ubuntu 9.3.0; 2025
Ubuntu guide 9.3.2/9.3.3; Lenovo Linux 9.3.3 package for Ubuntu 24.
Do not confuse OEM utility with proven Ubuntu 26.04 boot driver.
The vendor 9.3.3 boot kernel SDK and actual ASUS LUN signature
remain an integration/acceptance gate, not a new algorithm design
or evidence of nonexistence.

## One authority and runtime composition

```text
ASUS PHYSICAL HOST — Ubuntu LinuxDev
  ├── GNOME desktop, Radeon 8060S, ROCm, LLM
  ├── Windows data carrier + existing AMD RAID logical disks
  ├── native swap/zswap, cgroups v2, host firewall
  └── systemd-nspawn: FACTORY MANAGER
        ↑ Factory control authority begins HERE
        ├── private user/mount/PID/network namespaces, dedicated host UID
        ├── device allow /dev/kvm; NO /dev/nvme, /dev/dri, host root
        ├── explicitly permitted Factory VHDX file catalog
        ├── libvirt qemu:///session (never qemu:///system)
        └── one QEMU/KVM FACTORY VIRTUAL MACHINE
              ├── small independent guest Linux supervisor
              ├── nspawn: Ephemerd + embedded containerd/OCI jobs
              ├── nspawn: WSL-Distro-A, original ext4.vhdx A
              ├── nspawn: WSL-Distro-B, original ext4.vhdx B
              └── nspawn: WSL-Distro-N, original ext4.vhdx N
                  + associated persistent Btrfs/data VHDX per distro
```

Host does NOT expose system libvirt or root shell. Factory owns
QEMU within its narrow UID/mount/device scope; libvirt session
daemon and QEMU run unprivileged. Guest WSL instances are **sibling
system containers, not one master Ubuntu WSL root**. Ephemerd is
another guest sibling, independently repairable by Factory even
when normal CI cannot run. Candidate code has no management/host
credentials; guest containerd and Workbench are separate boundaries.

Factory can mount/modify ALL Factory-authorized disks attached to
its VM, because it manages QEMU; guest sibling isolation is not
confidentiality against this trusted admin. No private protected WSL
disks can be attached without explicit authority. LinuxDev host
retains the physical safety policy and device catalog.

## Update, snapshot, rollback and Secure Boot architecture

[LIFECYCLE.md](LIFECYCLE.md) is the selected release contract.
One new Linux RAID LUN has its own 2 GiB ESP, 4 GiB ext4 /boot
and independent LUKS2 passphrase-protected Btrfs root. The system
uses **Snapper** for host rollback, with separate home, snapshot,
swap and Factory VM state. The host keeps both current and
last-known-good signed kernel/initramfs/rcraid pairs.

Factory supervisor qcow2 may be rolled back by Factory;
**canonical WSL ext4.vhdx and companion data VHDX may NOT be
included in QEMU or host system snapshots.** Each distro
has its own targeted off-device backup/restoration.

**Firmware Secure Boot remains ON** for both Windows TPM+PIN
BitLocker installations. Ubuntu Canonical-signed shim/GRUB/kernel
plus module-signing-only MOK for patched AMD rcraid. No special
LinuxDev TPM+PIN/UKI or firmware key replacement. Ubuntu initramfs
is not authenticated by stock Secure Boot.

Host installation is via **Ubuntu 26.04 Subiquity/curtin custom
storage** to the explicitly verified new RAID LUN, followed by
official Ubuntu Desktop packages for GNOME; guided Desktop
storage cannot be relied on for exact LUKS+Btrfs snapshots.

## Dynamic UMA memory

One kernel-owned pool, no fixed 8/16 GB reserve for Ephemerd.
The VM has a guest-visible upper bound but only faulted/resident
pages consume RAM. QEMU virtio-balloon free-page reporting returns
unused pages and guest ballooning reclaims more when enabled.
Host cgroup-v2 resource priorities (`MemoryLow/High`, PSI,
systemd-oomd), zswap and native NVMe-backed swap reclaim
cold CPU/VM memory. Guest inner cgroups prioritize separate
WSL/CI children. Do not promise guest cache can be instantly
reclaimed or GPU-pinned pages swapped. No extra bespoke
always-on memory-balancing service.

## Immutable cross-OS storage rule

Windows WSL2 and native LinuxDev must **never** concurrently
write the same image. On Linux, the permitted original VHDX
attaches directly as a QEMU virtual disk, then ext4 is mounted
within the common guest and started as an independent `nspawn`
OS tree. Explicit shutdown/flush/unmount/close before Windows
regains the file. Supplementary Btrfs image belongs to its
original distro. No routine export, import, WIM-style conversion,
chown, repeated package installation, sync or parallel copies.
Do not mount writable NTFS in Linux when Windows Fast Startup
has left it hibernated.

## Verified RAID installation research

The machine-specific Linux RAID driver and installation investigation is
[RAID_INSTALL_FA401EA.md](RAID_INSTALL_FA401EA.md). AMD 9.3.3.302's official
Linux blob requires **an APU-specific kernel/feature-mask and NVMe trap
compatibility adaptation** on recent kernel versions; the most concrete
prior work is DesktopECHO/rcraid-nvme (pinned main `7ef6506b1dc6`).
Its existing installer is **NOT appropriate unmodified** for Ubuntu 26.04
Desktop/multiple Windows ESPs; see the demonstrated Calamares-only detection,
first-FAT ESP pick and target-kernel mismatches in that report. Use explicit
array and ESP identification, never raw NVMe. This is an engineering
integration path, not a claim of proven ASUS boot.

## Deployment contract

1. Use the actual OEM AMD Linux RAID 9.3.3.302 RPM plus pinned and audited
   APU/kernel compatibility port; verify existing ASUS multi-LUN identity,
   DKMS/target-initramfs/module signing and Secure Boot under Ubuntu 26.04.
   Do not run the upstream auto-installer or assume its ESP selection is safe.
2. Non-destructively provision LinuxDev as independently bootable
   OS; preserve both Windows and their recovery protections.
3. Apply declarative `factory-manager.nspawn` policy: allowed
   VHDX files, dedicated UID, `/dev/kvm` and restricted networking.
4. Install ordinary session libvirt and QEMU, create one tiny
   guest supervisor root and a registered nspawn machine for each
   WSL distro **plus separate Ephemerd**. Use a disposable source
   image first to establish mount/UID preservation; then attach
   the canonical image with exclusive ownership.
5. Qualification: two or more original WSL distros round-trip
   independently with Windows; Ephemerd runs real Factory CI;
   Factory repairs stopped Ephemerd and redefines its own VM
   without host administrator rights; negative tests protect
   unrelated host disks and host service interfaces.
6. Exercise memory pressure with simultaneous real native LLM
   workload and lower-priority Factory CI: guest free-page
   reporting/host swap/desktop responsiveness; preserve data.
7. Retire Windows-only Ephemerd/runner-syncd only after its
   accepted 24/7 dispatch/recovery contract has been replaced.

## Evidence

- AMD official Ubuntu Linux RAID (2025):
  https://docs.amd.com/api/khub/documents/l_VvImC0IX9mjsLPOPymFw/content
- AMD Linux RAID 9.3.0 driver:
  https://www.amd.com/en/support/downloads/drivers.html/chipsets/strx4/trx40.html
- Lenovo 9.3.3 OEM Linux/Ubuntu24:
  https://support.lenovo.com/us/en/downloads/ds578298-amd-software-based-raid-linux-utility
- KVM inside nspawn actually works:
  https://github.com/systemd/systemd/issues/38297
- Session libvirt is ordinary-user authority:
  https://ubuntu.com/server/docs/how-to/virtualisation/libvirt/
- Linux QEMU isolation:
  https://www.qemu.org/docs/master/system/security.html
- Original WSL image ownership:
  https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk
- QEMU balloon free-page reporting:
  https://wiki.archlinux.org/title/QEMU
- Ephemerd Linux containerd implementation:
  https://github.com/ephpm/ephemerd/blob/main/docs/architecture/embedded-containerd.md

**Single source of the selected topology:** this file; other background
research passages in ARCHITECTURE.md are historical where contradicted
by this decision.
