# LinuxDev — executable product rollout plan

**As-of 2026-10-17. State: research/architecture only; NO OS installation
authorized.** Tracking: [Linux issue #17](https://github.com/evanmih-cmd/linux/issues/17).

## Selected release composition

**Single product architecture — no alternative implementation branches.**

| Boundary | Product |
| --- | --- |
| Physical OS/desktop | Ubuntu 26.04 LTS Desktop, GNOME, native amdgpu |
| Native inference | ROCm/llama.cpp directly on host; Radeon 8060S |
| Host-owned Factory guard | systemd-nspawn `factory-manager`, private user namespace, narrow `/dev/kvm` device grant, AppArmor, host firewall/cgroup |
| Factory virtualizer authority | libvirt **`qemu:///session` INSIDE nspawn**, no host/system libvirt |
| Shared guest | ONE minimal Linux QEMU/KVM guest using a separate supervisor root image |
| Multiple WSL environments | Original WSL distro **each in its own guest nspawn**, each separate original ext4.vhdx and other durable VHDX as needed |
| Ephemerd | Linux backend/embedded containerd in **its own guest nspawn**, separate from all WSL distros |
| RAM | Host cgroups-v2 / zswap and native swap; guest free-page reporting/ballooning; no permanent resident allocation of advertised guest maximum |
| RAID | AMD vendor Linux `rcraid` driver/SDK product line prioritized; unchanged existing WinOps RAID LUNs and WinHome |
| Data | Previously researched NTFS shared capacity with dynamic VHDX; clean exclusive Windows/Linux ownership |
| Boot | Independent Linux, WinHome, WinOps boot/recovery |

## P0 — ASUS FA401EA RAID deployment via existing AMD APU driver adaptation

**Implementation authority:** [RAID_INSTALL_FA401EA.md](RAID_INSTALL_FA401EA.md).
Vendor 9.3.3.302 + pinned APU/kernel patches are the concrete researched
path. The upstream auto-installer cannot be run unchanged on this machine:
Calamares-only mount detection versus Ubuntu Desktop Subiquity; selects
first-found vfat ESP (could be Windows); chroot may build against live
kernel rather than new installed kernel. Explicit identity/target-ESP,
version-matched signed module, initramfs proof are mandatory.

### Previously recorded vendor context

**Evidence correction:** RAIDXpert2 already has native AMD Linux drivers,
not merely an experimental reverse-engineered port.
AMD distributes Ubuntu driver 9.3.0.00276; March 2025 AMD Ubuntu
guide covers 9.3.2/9.3.3, DKMS/driver_sdk/MOK on Ubuntu; Lenovo's
Nov 2025 OEM Linux Utility 9.3.3 covers Ubuntu 24/RHEL9.

AMD's latest 9.3.3.00291 Windows release supports Ryzen AI Max
family, but is NOT evidence of an Ubuntu 26.04 kernel driver.
The relevant cross-OS compatibility fact is actual
controller/metadata/multiple LUN topology and 26.04 kernel API,
not CPU marketing family.

**Implementation:** obtain the supported 9.3.3 vendor/OEM Linux
kernel-driver artifact and its exact installation/SDK update method;
identify exact ASUS RAID PCI topology and virtual LUN geometry from
already available WinOps evidence. Establish module signing and
kernel upgrade continuity with Secure Boot, unambiguous LUN/ESP
presentation, Windows recovery, and raw NVMe member protection.
The OEM package is labelled Utility; don't claim it necessarily
contains `rcraid.ko` without checking. Do NOT run an installer on
the raw NVMe, alter existing arrays or import them through guessed
mdadm mappings.

**P0 release gate:** validated non-destructive presentation of
existing WinOps and future Linux logical LUNs and a recoverable
Ubuntu 26.04 boot path. Driver existence is PROVEN; exact
ASUS/26.04 acceptance is NOT. Keep both Windows boots intact.

## P0B — single recovery-capable Linux host image

Normative contract: [LIFECYCLE.md](LIFECYCLE.md).
Select exactly the intended Linux RAID virtual LUN, create
its own ESP/boot and LUKS2+Btrfs subvolumes using
Subiquity/curtin custom storage, followed by official
Ubuntu GNOME packages. Use stock Snapper for root
snapshots; qualify real default-subvolume boot rollback,
not Ubuntu hard-coded `subvol=@`. Retain separate
old kernel+initramfs with exact signed `rcraid`.
Keep firmware Secure Boot on for Windows BitLocker;
enroll module-signing-only MOK and preserve off-laptop
Windows/LUKS recovery.

## P1 — multiple canonical WSL2 roots, independent per guest

**Do not equate WSL with one Ubuntu distro.** There may be many
distinct WSL2 distros, with divergent installed packages/accounts
and persistent extension disks. Each distro is an independently
named nspawn in the **one common Factory Linux VM**.

The host unlocks designated shared NTFS carriers and makes only
Factory-authorized VHDX files available to the management nspawn.
QEMU session VM attaches VHDX *directly* using `virtio-blk`.
Guest mounts every corresponding ext4 root separately, then starts
a distinct `systemd-nspawn` system container per distro. There
is no requirement to boot an existing WSL root as the VM's kernel/root.
Small independent guest supervisor OS can be maintained without
rewriting WSL OS trees. Supplementary Btrfs VHDX for runner02 remains
bound to the proper original distro, not substituted with ext4.

**Single writer:** Windows WSL2 shuts down and detaches before Linux
attaches; Linux guest stops every nspawn, unmounts each ext4,
shuts down, QEMU closes images, NTFS flushes, before Windows WSL
starts. Neither simultaneous RW nor synchronization/cloning is
accepted. WSL root numeric UID/GID must stay untouched: no
recursive `chown`; use idmapped mounts where needed.

**Trust:** the host permits only specifically authorized Factory
VHDX files. The Factory manager (QEMU administrator) can read/write
them, regardless of sibling nspawn confinement; independently
protected/operator-only WSL filesystems aren't exposed. No
hidden assumption that there is exactly one WSL root.

**Windows Fast Startup:** disable on Windows installation(s) owning
the shared writable NTFS carrier before native Linux RW access.
This requirement is different from today's two isolated Windows OS
volumes.

## P2 — graphical host and local high-memory LLMs

Deploy a normal GNOME desktop, native amdgpu kernel driver and graphics
stack; no project-specific Factory runtimes or SDKs in LinuxDev root.

ROCm 7.14.1 AMD matrix supports Radeon 8060S/gfx1151 on Ubuntu 26.04.
Ubuntu 26.04 itself ships **ROCm 7.1.0** packages and
CI-tests gfx1151 with `llama.cpp`; these are distinct versions:
choose distro packages first (Product First), pin newer ROCm only if
model/backend performance or compatibility establishes that need.

For the **actual 64 GB unified memory** FA401EA, aim for an inference workload
that **cannot fit in the user's current Windows 48 GB usable GPU window**,
while reserving real system RAM for Linux desktop, Factory/ephemerd and
model KV cache. GTT addressability != physically free RAM. Do not promise
the entire 64 GB to a model. Use actual load+throughput+memory pressure
and end-to-end agent-serving behavior for acceptance. Main native runtime:
`llama-server` with `gfx1151` ROCm; Vulkan alternative assessed only
where it materially helps.

## P2A — elastic RAM/swap policy, not fixed partitions

The selected Factory KVM guest has **no permanently reserved full VM
RAM footprint**. The Linux host manages demand-paged QEMU memory along
with GUI and native LLM through cgroups v2 and host swap. The guest
independently manages its internal nspawn child cgroups. Implement using supported systemd cgroup-v2
slice controls: **MemoryLow** best-effort protection for active GUI/LLM,
modest **MemoryMin** only for critical host survivability,
**MemoryHigh** pressure/reclaim for lower-priority loads when justified,
**MemoryMax** only as an OOM last-resort guard, **MemorySwapMax** policy
and `systemd-oomd`/PSI selection at a safe service boundary.

Use dynamically populated **zswap backed by real native NVMe swap**
where compatible. This actually evacuates cold pageable background
pages to disk if necessary; compressed-RAM-only zram alone does not
provide the same oversubscription property. Never place a swapfile on
an unsafe Windows-hibernation shared volume. Protect confidential
swap storage appropriately. GPU-pinned allocations are not promised
swappable; model weights+KV+GUI require physical RAM headroom.

The acceptance is **not** "sum of reservations <= 64 GB". It is
measured responsive desktop + genuinely useful native LLM larger
than Windows 48 GB and simultaneous background Factory behavior,
observing memory pressure, swap usage and CI job survival/preemption.
Do not introduce a resident memory-balancer daemon.

## P3 — delegated QEMU autonomy and separate Ephemerd/WSL guests

1. Physical host creates and enforces a `factory-manager`
   `systemd-nspawn` boundary. Dedicated unprivileged UID;
   no `qemu:///system` socket; grant only `/dev/kvm`, approved VHDX
   paths, whitelisted Internet/management network, cgroups.
2. Factory runs **libvirt `qemu:///session` inside nspawn** and manages
   its own **one** QEMU guest. This separates Factory's VM
   control authority from LinuxDev physical root. An actual
   systemd issue confirms that bound `/dev/kvm` +
   `DeviceAllow=/dev/kvm rw` makes `qemu-kvm` run inside nspawn;
   Ubuntu docs establish session libvirt's ordinary-user privileges.
   The *combined topology* requires a real acceptance demonstration,
   not an assumption based on individual capabilities.
3. Boot one small independent Linux guest supervisor. Attach each
   authorized original WSL `ext4.vhdx` as virtual disk; start an
   isolated, separately named guest-side nspawn for every WSL
   distribution. Keep extra persistent disks with their owner.
4. Start Ephemerd Linux v0.2.20 as a separate guest nspawn using its
   embedded containerd/overlayfs/CNI + stock OCI runner and the
   accepted Factory Workbench. Guest inner nspawn can grant necessary
   OCI privileges **within the VM kernel**; the security of the
   physical host is determined by the outer KVM+nspawn boundary,
   not by unproven nested userns/rootless semantics.
5. Factory owns VM definition, update/restart/snapshot, guest
   systemd and Ephemerd repair via ordinary libvirt session,
   guest SSH/console and stock tools **even when CI/Ephemerd is
   stopped**. No custom physical LinuxDev updater.
6. Negative tests: candidate CI cannot use Factory's session-libvirt
   socket, `/dev/kvm`, host RAID/Windows/desktop/LLM, sibling
   WSL disks, or unapproved network; Factory manager itself
   cannot access host system-libvirt/root, kernel modules,
   unrelated files or raw disks.
7. Fault + recovery test: Ephemerd stopped and repaired by Factory;
   guest kernel fault recovered by Factory via its VM; only
   physical host/hypervisor damage needs operator action.
8. Measure host RSS/PSI/zswap/NVMe swap, QEMU balloon
   free-page reporting, guest page cache pressure and native
   LLM throughput while concurrently running at least two
   separate WSL containers plus the Ephemerd service.

**KVM memory contract:** virtual capacity is not reserved RAM.
`virtio-balloon` free-page reporting returns freed guest pages
without a custom updater. Cold host QEMU memory remains subject
to host reclaim/swap. Reporting alone cannot reclaim a guest's
live cache; do not claim perfect instant reclamation or a full
64 GB iGPU allocation. Host controls cgroup pressure, Factory
controls the guest's inner service priority.

## P3B — updates and snapshots across different state owners

[LIFECYCLE.md](LIFECYCLE.md) defines an explicit lifecycle:
Snapper @system snapshots with retained compatible signed
kernel/initramfs/rcraid; APT unattended security updates
without automatic reboot; kernel/DKMS coordinated activation.
Separate, powered-off **supervisor-only** qcow2 snapshots
for Factory; DO NOT snapshot VHDX backing disks or rewind
other Windows-registered WSL images. Use per-distro
offline restic backup plus verified external image/Veeam
backup, not unproven VSS of a live WSL VHDX.
Test rollback failures and off-device recovery before release.

## P4 — Windows-side Ephemerd retirement (separate release)

The existing Windows Ephemerd+FactoryRunnerSyncd (#481/#473)
remains operational until a shared Linux-guest/WSL lifecycle
actually replaces its accepted availability, CI/network and
autonomous update contracts. Merely installing systemd inside
WSL does not keep WSL running. This is a migration acceptance
requirement, **not** permission to delete working infrastructure.

## P4 — rollback and release, after P0-P3 gates

- Native installer target selection must be explicit and positive;
  firmware selection must not silently join WinHome, WinOps and LinuxDev
  into a single fragile Windows Boot Manager dependency.
- The Windows hardware audit issue #9 remains a frozen record, not the
  LinuxDev work tracker.
- Host provisioning should be declarative/pinned using Ubuntu product
  packages and ordinary distro configuration; avoid custom service code
  when `systemd`, `nspawn`, `cryptsetup`, QEMU, Ephemerd provide the feature.
- Final acceptance: independent WinHome + WinOps boot/recovery; **at least
  two separate original WSL2 roots** round-trip with Windows independently;
  Factory manages its QEMU guest while unable to manage LinuxDev; a separate
  Ephemerd nspawn completes real CI and is repaired while stopped; useful
  desktop; >48 GB native LLM workload; normal update/reboot recovery.

## Evidence links

- [Real ASUS WinOps RAID layout](https://github.com/evanmih-cmd/linux/issues/9#issuecomment-6110011694)
- [AMD ROCm 7.14.1 matrix](https://rocm.docs.amd.com/en/docs-7.14.1/compatibility/compatibility-matrix.html)
- [Ubuntu 26.04 ROCm/gfx1151 CI](https://documentation.ubuntu.com/release-notes/26.04/changes-since-previous-interim/)
- [AMD Ubuntu RAID guide: supported platform families](https://docs.amd.com/api/khub/documents/l_VvImC0IX9mjsLPOPymFw/content)
- [AMD Linux RAIDXpert2 driver 9.3.0 and supported platforms](https://www.amd.com/en/support/downloads/drivers.html/chipsets/strx4/trx40.html)
- [AMD Ubuntu RAID driver 9.3.2/9.3.3 guide](https://docs.amd.com/api/khub/documents/l_VvImC0IX9mjsLPOPymFw/content)
- [Lenovo OEM 9.3.3 Ubuntu24 RAID package](https://support.lenovo.com/us/en/downloads/ds578298-amd-software-based-raid-linux-utility)
- [Actual KVM inside systemd-nspawn](https://github.com/systemd/systemd/issues/38297)
- [Ubuntu libvirt qemu session unprivileged](https://ubuntu.com/server/docs/how-to/virtualisation/libvirt/)
- [Ephemerd Linux/Windows backend](https://github.com/ephpm/ephemerd)
- [Ephemerd security and privileged Docker warning](https://github.com/ephpm/ephemerd/security)
- [Libvirt VM network and firewall](https://libvirt.org/firewall.html)
- [Ubuntu 26.04 nspawn user namespaces/idmapped mounts](https://manpages.ubuntu.com/manpages/resolute/man1/systemd-nspawn.1.html)
- [Ubuntu systemd-container 259.5](https://packages.ubuntu.com/resolute/systemd-container)
- [Kernel cgroup-v2 memory reclaim](https://docs.kernel.org/admin-guide/cgroup-v2.html)
- [Kernel zswap compression/writeback](https://docs.kernel.org/admin-guide/mm/zswap.html)
- [Upstream Ephemerd embedded containerd](https://github.com/ephpm/ephemerd/blob/main/docs/architecture/embedded-containerd.md)
- [QEMU external-kernel Linux direct boot (fallback)](https://www.qemu.org/docs/master/system/linuxboot.html)
- [WSL systemd does not keep its VM alive](https://learn.microsoft.com/en-us/windows/wsl/systemd)
- [Incus VM versus container isolation](https://linuxcontainers.org/incus/docs/main/explanation/containers_and_vms/)
