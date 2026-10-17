# LinuxDev — executable product rollout plan

**As-of 2026-10-17. State: research/architecture only; NO OS installation
authorized.** Tracking: [Linux issue #17](https://github.com/evanmih-cmd/linux/issues/17).

## Target release (selected starting composition)

| Boundary | Product candidate / disposition |
| --- | --- |
| Native host OS/desktop | **Ubuntu 26.04 LTS Desktop**, stock GNOME, Linux 7.0/inbox amdgpu |
| Local GPU inference | **llama.cpp (ROCm/HIP, gfx1151)**, native server; Ubuntu ROCm distro packages first; AMD ROCm 7.14.1 optional pinned version when needed |
| Factory & child workloads | Original WSL2 `ext4.vhdx` mounted **once** and launched in `systemd-nspawn`; Ephemerd inside same namespace child if secure nested containerd proves workable; otherwise one shared KVM fallback |
| Shared AI user/work data | inherited **NTFS shared capacity pool -> dynamically expanding ext4 VHDX**; WSL2 native `wsl --mount --vhd`, Linux `ntfs3 -> qemu-nbd -> ext4` |
| Factory CI isolation | **User-namespaced, AppArmor/namespace-confined nspawn child** with embedded-containerd Ephemerd (qualification required); Factory control retains in-child admin, no LinuxDev-root updater |
| Host memory | **One elastic cgroup-v2 RAM pool, zswap plus native NVMe swap**; memory.Low/High/Swap, PSI and systemd-oomd priority policy, no VM preallocation |\n| Physical SSD2 storage | **Existing AMD RAIDXpert2 LUN**, not a blank disk; no accepted Linux driver or installation layout yet |
| Dual-boot | independent firmware-selectable boot and recovery paths; Windows Home and Pro retained untouched |

This plan does not replicate `portable/` crypto-workstation mechanisms, require
a Factory-specific host OS, run the inference GPU inside a VM, or make a separate
new Linux distro the canonical replacement for old WSL2 root filesystems.

## P0 — resolve the **actual** AMD RAID LUN boundary first

Observed on physical ASUS at [issue #9 snapshot](https://github.com/evanmih-cmd/linux/issues/9#issuecomment-6110011694):
- SSD1: existing Windows Home.
- SSD2 Lexar NM790 4TB: **AMD RAID Array 2**, actual WinOps Pro C: and
  independently prepared EFI + Windows Recovery partitions.
- Windows WinPE required `rcbottom -> rcraid -> rccfg` driver sequencing to
  avoid seeing raw NVMe instead of the intended logical RAID target.

No new install target is accepted unless a Linux storage path can safely
distinguish already allocated logical LUNs from their raw RAID-member SSD:

A. Investigate AMD's published Linux RAID stack against the actual ASUS
   **RAID controller PCI ID, firmware and on-disk metadata/LUN layout**,
   Ubuntu 26.04 kernel, kernel updates, module signing/Secure Boot, TRIM,
   shutdown/recovery and **single-NVMe virtual disks**, not generic
   two-disk RAID0/1. This is **independent of CPU/GPU SKU**.

B. Research `joeytroy/amd-raid-driver` as a *non-authoritative candidate*:
   it explicitly claims Ryzen AI Max support and Linux 7.0, but physical
   proofs are on TRX50 (two Crucial T700), so it does not establish safe
   access to the actual ASUS multiple-LUN storage. Do not accept only
   `/dev/rcraid0` existing, or a read-only listing, as evidence that
   both current Windows OS/recovery images will remain bootable after writes.

C. Independently evaluate an accessible non-RAID Linux root on the ASUS
   **without changing RAID firmware mode**. Its data/capacity continuity
   trade-offs versus an RAIDXpert2 LUN must be explicit. No third disk
   may be silently assumed: both existing M.2 slots are occupied.

D. Freeze host storage/boot implementation until one product route has
   a support/recovery story. If neither is credible, flag a genuine
   architecture conflict instead of improvising a destructive workaround.

**P0 outputs:** exact safe block-device namespace, independent ESP/boot
topology, encryption/unlock and Windows rollback, supported kernel-upgrade
path, and explicitly established target capacity. Any future live check
must be controlled **read-only until the candidate is accepted**; the raw
RAID member must never be formatted/mounted read-write accidentally.

## P1 — preserve original WSL2 systems, not just shared models

Previous research *already decided* the cost-effective capacity solution:
native Windows NTFS storage containing a dynamically expanding VHDX whose
ext4 content is shared between WSL2 and native Linux. Do not reopen general
Storage Spaces/ZFS/LVM/Paragon research without new contradicting evidence.

There are two distinct persistent image classes, both to preserve:
1. **WSL distro root `ext4.vhdx`** — user accounts, package installs,
   software/configuration/service state and workspaces retained verbatim.
2. **Shared AI-data VHDX** (and any current dedicated Docker/Btrfs images)
   — agent data, model files, repositories, authorized shared files,
   per-user/mode isolation; no second synchronized canonical copies.

**First candidate: host nspawn.** Windows WSL2 cleanly detaches original
`ext4.vhdx` -> LinuxDev obtains exclusive access to the NTFS/VHDX
carrier -> `qemu-nbd` exposes ext4 -> an appropriately isolated
`systemd-nspawn` launches the **original WSL OS tree** and Ephemerd
Linux within the same Factory namespace boundary -> clean shutdown,
flush, detach -> Windows WSL2 resumes same filesystem. The VHDX is
not itself a VM. **No separate Ephemerd VM.**

With `--private-users=pick`, insist on
`--private-users-ownership=map`: `auto` can silently fall back to
recursive file ownership changes that would invalidate WSL numeric
UID/GID state. If idmapped mounts don't work on the exact ext4
carrier, stop and change runtime rather than touching owners.
Nested OCI/containerd network, cgroups and AppArmor need real E2E
qualification. If that cannot be done without host privilege,
use **one KVM/libvirt guest** for both WSL root and Ephemerd instead,
potentially using virtio-balloon/virtio-mem to avoid a fixed RAM
allocation.

**Compatibility gates:** Ubuntu 26.04 WSL distributions, uid/gid, systemd
units, cgroups, independent persistent Docker/Btrfs volume mount order,
GitHub runner/agent state, network and device/host integration, absence of
Windows-only paths where Linux job runs. No mandatory re-install/export/import
on each OS switch. Test writes Windows->Linux->Windows **and**
Linux->Windows->Linux to the *same* data, with recovery from clean detach;
no concurrent RW ownership.

**Windows fast startup:** Disable it on the Windows host(s) which own a
shared writable NTFS carrier, before allowing Linux write access. Do not
mistake the current isolated Home/WinOps arrangement for this future
shared-data dual-boot design.

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

No reserved per-VM memory quota in the preferred `systemd-nspawn` mode.
The host kernel makes on-demand memory allocation decisions across GUI,
native LLM and Factory. Implement using supported systemd cgroup-v2
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

## P3 — one nspawn child: WSL root + Ephemerd + Factory control

**Preferred for economic and elastic UMA memory reasons:**
`systemd-nspawn` with `--private-users=pick` and
`--private-users-ownership=map` (no recursive chown), private
PID/mount/network namespaces, tightly controlled cgroups delegation,
host-side AppArmor and network firewall. Root inside Factory can
update the Factory WSL OS, embedded-containerd Ephemerd and OCI images,
but **must have no root privileges or broad capabilities in the
physical host's initial user namespace**.

Stock upstream Ephemerd for Linux uses embedded containerd (runc,
overlayfs, CNI bridge/iptables) and best-effort AppArmor confinement.
The exact nested restrictions must be positively proven: real
OCI job, real Docker-compatible build, network ACLs, nested cgroup
enforcement, and no fallback that disables necessary confinement or
adds broad host SYS_ADMIN/NET_ADMIN authority.

**Use a disposable *clone* of the existing WSL root for these
tests.** Validate that the map mode keeps numeric ownership unmodified.
If no safe nesting path exists, the lower-memory choice loses to
the necessary stronger security boundary: use one KVM VM containing
both the original WSL root and Ephemerd. KVM also offers ballooning /
virtio-mem, so don't assume it necessarily consumes an immutable
initially declared RAM quota.

**Independent Factory control:** in-child trusted controller (not
the CI job process) can execute `systemctl` and change images/daemon
when Ephemerd is deliberately stopped. No bespoke host-side updater.
Host owns the nspawn service and resource/network/security policies
only, not ordinary Factory upgrades. Ordinary untrusted jobs have no
admin credential, root containerd socket or host-owned sockets/paths.

**Acceptance:** same canonical WSL filesystem roundtrip with Windows;
real Ephemerd Factory CI in nested nspawn; host privilege and network
negative tests; stopped daemon recovery without host admin; desktop +
LLM priority, zswap/NVMe swap and controlled memory pressure with
no static Factory RAM reservation.

Under Windows, a later optional simplification is running the
Linux Ephemerd backend from the very same original WSL2 filesystem.
This is **not** yet qualified, including Windows-side unattended WSL
lifetime. Do not retire current Windows service beforehand.

## P4 — rollback and release, after P0-P3 gates

- Native installer target selection must be explicit and positive;
  firmware selection must not silently join WinHome, WinOps and LinuxDev
  into a single fragile Windows Boot Manager dependency.
- The Windows hardware audit issue #9 remains a frozen record, not the
  LinuxDev work tracker.
- Host provisioning should be declarative/pinned using Ubuntu product
  packages and ordinary distro configuration; avoid custom service code
  when `systemd`, `nspawn`, `cryptsetup`, QEMU, Ephemerd provide the feature.
- Final acceptance: independent WinHome + WinOps boot/recovery; original
  WSL2 root state changes in both directions; useful desktop; representative
  Ephemerd job; useful >48GB-local-LLM workload; normal update/reboot recovery.

## Evidence links

- [Real ASUS WinOps RAID layout](https://github.com/evanmih-cmd/linux/issues/9#issuecomment-6110011694)
- [AMD ROCm 7.14.1 matrix](https://rocm.docs.amd.com/en/docs-7.14.1/compatibility/compatibility-matrix.html)
- [Ubuntu 26.04 ROCm/gfx1151 CI](https://documentation.ubuntu.com/release-notes/26.04/changes-since-previous-interim/)
- [AMD Ubuntu RAID guide: supported platform families](https://docs.amd.com/api/khub/documents/l_VvImC0IX9mjsLPOPymFw/content)
- [community Linux rcraid](https://github.com/joeytroy/amd-raid-driver)
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
