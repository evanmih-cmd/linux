# LinuxDev — executable product rollout plan

**As-of 2026-10-17. State: research/architecture only; NO OS installation
authorized.** Tracking: [Linux issue #17](https://github.com/evanmih-cmd/linux/issues/17).

## Target release (selected starting composition)

| Boundary | Product candidate / disposition |
| --- | --- |
| Native host OS/desktop | **Ubuntu 26.04 LTS Desktop**, stock GNOME, Linux 7.0/inbox amdgpu |
| Local GPU inference | **llama.cpp (ROCm/HIP, gfx1151)**, native server; Ubuntu ROCm distro packages first; AMD ROCm 7.14.1 optional pinned version when needed |
| Factory & child workloads | Original **WSL2 ext4.vhdx** boots/mounts in **the same ONE Factory KVM guest that runs Ephemerd** (preferred); no extra VM for WSL. A direct host nspawn route needs no WSL VM but leaves host/daemon security analysis; neither is qualified yet |
| Shared AI user/work data | inherited **NTFS shared capacity pool -> dynamically expanding ext4 VHDX**; WSL2 native `wsl --mount --vhd`, Linux `ntfs3 -> qemu-nbd -> ext4` |
| Factory CI isolation | **The one shared Factory KVM/libvirt guest**, also serving its original WSL2 OS root; embedded-containerd ephemerd and independent in-guest Factory controller, no host-updater |
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

**Preferred one-VM flow:** Windows clean shutdown of WSL2 and VHDX ->
LinuxDev exclusive ownership -> QEMU/KVM direct-boot guest kernel/initrd
with the **original Factory WSL2 ext4.vhdx as guest root** -> run Factory
control processes and Ephemerd inside this very same VM -> guest clean
shutdown -> host detaches VHDX -> Windows WSL2 resumes same root state.
A guest kernel/initrd does not require placing a new bootloader into the
original WSL filesystem. This is a supported QEMU **mechanism**, not yet
qualified for this specific WSL image.

If other Factory-owned WSL roots must coexist, attach their own VHDX as
virtual disks and run via nspawn *inside that single VM* when suitable.
Avoid presenting private/protected WSL images to guest-root at all.
For a WSL root that only needs Linux namespace semantics, **direct
LinuxDev nspawn needs no VM**; however, this doesn't give rootful Ephemerd
host-kernel isolation, hence the unified guest is the lead choice.
No mandatory OS copy, distro recreation, synchronized roots or second
Ephemerd VM.

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

## P3 — ONE shared Factory guest, including Ephemerd and WSL root

**Correction 2026-10-17:** Do not create one VM to host WSL roots and
another VM to isolate Ephemerd. VHDX is not itself a VM, and an original
WSL root can be mounted/run without virtualized guest kernel. But when
a full guest is chosen for the **Ephemerd authority boundary**, reuse it
for the original Factory WSL environment.

**Preferred product:** QEMU/KVM + libvirt, one existing **Factory-owned
ext4.vhdx** as the guest Linux root (external guest kernel/initrd direct
boot, no separate cloned root), embedded-containerd Linux ephemerd as a
normal guest service, Factory controller as an independent guest process.
Other existing Factory WSL images can be attached as separate disks and
namespace containers inside the same VM, never two VM allocations by
default. Do not pass any personal/protected root image into a guest whose
root administration can read it.

**Authority:** trusted Factory controller can repair/update Ephemerd, its
images and guest packages via systemd and guest admin even when
Ephemerd/CI is stopped. Candidate-executed CI has no guest-admin key,
guest systemd control, direct containerd root control or host/libvirt
socket. Factory guest-root can intentionally mutate attached
Factory-owned WSL filesystems; that access is the trust relationship,
not an independent per-container secrecy boundary.

**Host boundary:** libvirt network/VM start and disk attach only; no
host-owned updater, host/RAID/raw block passthrough, home, private data,
GPU, credentials or libvirt socket in the guest. Guest network has
explicit deny guest-to-host and private LAN/VPN, not merely libvirt NAT.
Reserve native GPU inference for LinuxDev. One VM consumes measured
shared RAM; stop or adjust it when loading large LLMs.

**Windows follow-on possibility:** replace current Windows host ephemerd
and custom updater with the **same ephemerd Linux process installed in
the original WSL2 root** when Windows is the boot OS. This is NOT yet
proven: embedded-containerd Linux on WSL2 and runner contract must
pass; Windows service/autostart requires a liveness strategy because
WSL's systemd service alone will not keep WSL alive. Don't prematurely
retire the working Windows service.

**Acceptance:** one guest boots the **original WSL root** and also
runs real Ephemerd Factory job; same VHDX mutations visible after
Windows WSL2 round-trip; control plane can repair stopped Ephemerd
within the guest; hostile job cannot escalate to guest admin/host;
normal and emergency shutdown do not corrupt VHDX; real host RAM
impact measured. Second VM requires an separately justified
independent trust domain and product-owner decision.

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
- [QEMU external-kernel Linux direct boot](https://www.qemu.org/docs/master/system/linuxboot.html)
- [WSL systemd does not keep its VM alive](https://learn.microsoft.com/en-us/windows/wsl/systemd)
- [Incus VM versus container isolation](https://linuxcontainers.org/incus/docs/main/explanation/containers_and_vms/)
