# LinuxDev — executable product rollout plan

**As-of 2026-10-17. State: research/architecture only; NO OS installation
authorized.** Tracking: [Linux issue #17](https://github.com/evanmih-cmd/linux/issues/17).

## Target release (selected starting composition)

| Boundary | Product candidate / disposition |
| --- | --- |
| Native host OS/desktop | **Ubuntu 26.04 LTS Desktop**, stock GNOME, Linux 7.0/inbox amdgpu |
| Local GPU inference | **llama.cpp (ROCm/HIP, gfx1151)**, native server; Ubuntu ROCm distro packages first; AMD ROCm 7.14.1 optional pinned version when needed |
| Factory & child workloads | original persistent **WSL2 ext4.vhdx** environments; native Linux invocation via **qemu-nbd + systemd-nspawn** is the leading direct-use path; runtime compatibility not accepted yet |
| Shared AI user/work data | inherited **NTFS shared capacity pool -> dynamically expanding ext4 VHDX**; WSL2 native `wsl --mount --vhd`, Linux `ntfs3 -> qemu-nbd -> ext4` |
| Factory CI service | **ephemerd for Linux**, embedded containerd and same Factory OCI runner image; security boundaries reviewed separately |
| Physical SSD2 storage | **Existing AMD RAIDXpert2 LUN**, not a blank disk; no accepted Linux driver or installation layout yet |
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

A. Investigate AMD's published Linux RAID stack against the actual
   FA401EA/Ryzen AI Max platform, Ubuntu 26.04 kernel, kernel updates,
   module signing/Secure Boot, TRIM, shutdown/recovery, and **single-NVMe
   virtual disks**, not generic two-disk RAID0/1.

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

**Native Linux candidate flow:** exclusive VHDX ownership -> validated NTFS
carrier -> `qemu-nbd` exposing the VHDX -> kernel ext4 mounted -> original
root tree executed under `systemd-nspawn` with host-side integration bindings
only -> clean child shutdown + unmount + NBD disconnect -> Windows WSL2
resumes original root filesystem. Try a full VM only for a proven
guest-kernel-semantic incompatibility, not by default.

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

## P3 — Ephemerd without obsolete Windows layers

Factory's current deployment pins **ephemerd v0.2.20** for WinOps with
Windows HCS/Hyper-V Linux VM and uses the Factory-production OCI runner image.
On Linux run the product's existing **embedded-containerd OCI backend**;
do **not** recreate a Hyper-V VM or invent a permanent Docker runner stack.

Map the existing Factory GitHub App identity, image, DIND, dispatch, tokens,
secrets, network policy and Workbench/runner isolation onto the Linux
service. The Linux host uses a shared kernel rather than Windows ephemerd's
VM kernel boundary, so **do not assert identical security from OCI alone**.
Representative Factory CI Product/Technical jobs must actually complete,
with candidate-controlled code confined to its intended Workbench boundary.

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
