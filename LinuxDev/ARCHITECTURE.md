# LinuxDev — host architecture research

**Status: research / unapproved implementation decisions, 2026-10-17.**
Business authority: [BUSINESS_REQUIREMENTS.md](BUSINESS_REQUIREMENTS.md).

## Boundaries

```text
LinuxDev (Ubuntu 26.04 + native GPU/LLM)
  │ host-owned launch, storage exposure, cgroup policy
  └─ systemd-nspawn: factory-manager (Factory-owned authority)
       ├─ unprivileged libvirt qemu:///session, /dev/kvm only
       └─ QEMU/KVM: ONE common Factory Linux VM
            ├─ systemd-nspawn: ephemerd (embedded containerd + OCI)
            ├─ systemd-nspawn: WSL distro A (its original ext4.vhdx)
            ├─ systemd-nspawn: WSL distro B (its original ext4.vhdx)
            └─ systemd-nspawn: WSL distro N (... independent images)

Each VHDX is shared in TIME between Windows WSL2 and LinuxDev.
```

No Factory compiler, build tool, agent framework or project-specific SDK belongs
in the host root filesystem merely because a child uses it. Host components
are limited to desktop, platform drivers, guest/container runtime, storage,
recovery and native LLM execution.

## Recovered prior design: one shared AI workspace

**Historical source:** saved project conversation `Laptop suitability for LLMs`,
in the section about the ASUS dual-boot storage pool, WSL2 and native Linux.
This was already researched *before* LinuxDev was opened; do not treat its
storage topology as an undiscovered Greenfield design problem.

The previously preferred practical topology, **not yet installed or formally
accepted for this LinuxDev release**, was:

```text
ASUS internal NVMe storage
├── Windows OS volume(s)       native NTFS; independent boot/recovery
├── LinuxDev OS volume         native Linux system FS; independent boot
└── large shared NTFS data pool (dynamic free-space allocator)
    ├── Windows games/data     native Windows files
    ├── existing WSL distro VHDX files (as appropriate)
    └── AI-data.vhdx            dynamically growing VHDX
        └── ext4                one common /srv/ai
            ├── model and dataset storage
            ├── projects/agent workspaces
            ├── artifacts and caches
            └── Linux users/ownership/permissions
```

- Under WSL2: `wsl --mount --vhd` presents the shared **data** VHDX to Linux,
  so Linux-native filesystem rights and data have one physical copy.
- Under native Linux: mount the NTFS carrier, then `qemu-nbd` presents the
  **same data** VHDX and ext4. No data export/import or two-way file sync.
- Windows games and the Linux-native AI workspace draw from the **same free
  NTFS capacity**: dynamic VHDX allocates backing space as it grows; OS root
  partitions need not be thin-provisioned.
- Safe use requires exclusive ownership, clean guest unmount and NTFS flush;
  do not boot Linux with the shared NTFS volume left in Windows Fast Startup
  or hibernation state. Space reclamation on deletion requires a separately
  verified discard/compaction path, not just dynamic allocation on growth.
- Prior candidate comparison rejected Storage Spaces vs LVM-thin as a single
  interoperable local pool, judged OpenZFS-on-Windows immature at the time,
  rejected Paragon ext4 as a critical Windows games filesystem, and retained
  **NTFS + dynamic VHDX** as the most practical available composition.

**Crucial distinction:** the original discussion decided a **shared persistent
AI data filesystem**, not a proven way to boot the *entire original WSL2 root
image* unchanged on native Linux. Those are independent images/concerns:
`AI-data.vhdx` vs `ext4.vhdx` for a WSL2 distribution. LinuxDev's new explicit
BR-3/BR-4 additionally requires direct, bidirectional continuation of each
existing WSL2 root environment. Do not silently replace it with only the common
`/srv/ai` directory or a recreated Linux distro.

Consequently, **shared data pool selection is inherited research, not the
next open-ended architecture question**. The remaining targeted question is
the launch/host-integration semantics for original WSL2 system images, using
the established carrier where appropriate. The physical layout may need
reconciliation with the *current* ASUS dual-SSD/WinOps installation; historical
example partition sizes or locations are not authoritative.

## Clarification: RAID compatibility is not a Ryzen-AI-Max compatibility matrix

LinuxDev's AMD RAID risk is a **storage-controller and on-disk format**
interoperability question, not a GPU/CPU SKU whitelist. Ryzen AI Max is the
family name of the ASUS processor/APU, but it does not define the RAID
metadata format. The relevant evidence is the controller's actual PCI ID,
AMD RAIDXpert2 metadata/LUN layout, firmware presentation, Linux module
behavior, Secure Boot signing and the safe boot/update/recovery path.
A processor family missing from an old RAID driver document is at most
insufficient support evidence; it is **not proof of incompatibility**.
Never couple ROCm GPU compatibility gates with AMD RAID import gates.

## WSL2 on Linux — what is established

1. Microsoft WSL2 distributions store Linux ext4 filesystems in `ext4.vhdx`.
   Microsoft provides `wsl --import-in-place` to register an existing compatible
   `ext4.vhdx` on Windows. WSL2 kernel, launcher, Windows integration and host
   configuration are separate from the guest's ext4 filesystem.
2. QEMU supports the **VHDX image format**; `qemu-nbd` is a potential bridge
   for presenting an existing VHDX as a block device on native Linux.
3. `systemd-nspawn` can run an OS tree mounted from such a device as a Linux
   namespace container. This uses the LinuxDev kernel while preserving the
   guest's Linux root filesystem and its persistent changes. An alternative
   full-kernel VM may be required if actual workloads depend on guest-kernel
   semantics incompatible with a container.
4. None of the above **by itself** proves that a particular existing WSL2
   image (or its Docker volumes, Windows path mounts, host sockets and other
   non-image persistent state) is completely usable unchanged.

**Leading integration hypothesis (NOT validated on the existing images):**

```text
Windows: WSL2 launches original ext4.vhdx
         ↓ shut down WSL and Windows filesystem access safely
Shared canonical VHDX on mutually accessible persistent storage
         ↓ LinuxDev obtains exclusive writable ownership
Linux:   direct QEMU VHDX virtual disks → guest mounts each ext4 → per-distro nspawn
         ↓ stop guest, unmount, flush, detach cleanly
Windows: WSL2 resumes same ext4.vhdx with Linux modifications
```

This design aims for **one canonical mutable image**, no `wsl --export` /
`--import` cycle on every switch, no mandatory copy, no image conversion,
and no guest reinstallation.

**Blocking questions before approval:**
- VHDX physical placement and mount accessibility from BOTH operating systems.
  Linux already has **cryptsetup BITLK** support for BitLocker-compatible
  encrypted volumes and **ntfs3** read/write NTFS filesystem support; these
  are concrete candidates for accessing an encrypted NTFS volume holding the
  canonical VHDX, not a reason to abandon the requirement. The specific
  Windows volume/protectors and safe write workflow remain to be designed.
  Linux must not mount a hibernated/Fast-Startup Windows NTFS volume writable,
  and the host should not expose unrelated protected Windows OS contents to
  child workloads.
- Consistency of NTFS hosting the VHDX, clean Windows shutdown (hibernation /
  Fast Startup), ext4 journal handling, and exclusive access semantics.
- Existing WSL distro registration and absolute paths on Windows: moving a
  VHDX is not automatically equivalent to keeping Windows registration intact.
- WSL-specific `/mnt/c` paths, systemd/cgroups, DNS, clock, GUI integrations,
  Docker socket/volumes, devices, uid/gid mapping and dependent services.
- Whether the intended meaning of “as is” can be met by a containerized OS
  tree for **each** current child, or a guest kernel is genuinely necessary.

An independent copied Linux tree with periodic sync **fails BR-3/BR-4** as
a default architecture; preserving Git sources alone is not enough.

**Sources:**
- Microsoft, WSL disk space: https://learn.microsoft.com/en-us/windows/wsl/disk-space
- Microsoft, WSL mount VHD: https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk
- Microsoft, WSL import-in-place: https://learn.microsoft.com/en-us/windows/wsl/basic-commands
- QEMU images: https://www.qemu.org/docs/master/system/images
- QEMU image utility: https://www.qemu.org/docs/master/tools/qemu-img.html
- systemd-nspawn: https://man7.org/linux/man-pages/man1/systemd-nspawn.1.html
- cryptsetup BitLocker support: https://man7.org/linux/man-pages/man8/cryptsetup-luksopen.8.html
- Linux kernel ntfs3: https://docs.kernel.org/filesystems/ntfs3.html
- NTFS dual-boot/hibernation safety: https://manpages.debian.org/bookworm/ntfs-3g/mount.ntfs.8.en.html

## Selected virtualization and authority topology (2026-10-17)

**This supersedes the earlier nspawn-only Ephemerd candidate and the
incorrect one-WSL-distro-equals-the-VM-root design.**
The final architecture is **LinuxDev -> host nspawn management domain ->
unprivileged QEMU/KVM -> one common guest -> multiple guest nspawn
containers**, including a *separate* Ephemerd. Host and Factory
administration boundaries are deliberately different.

```text
PHYSCAL ASUS                 HOST-OWNED (Ubuntu 26.04 Desktop)
├─ GPU / LLM / operator GUI   (no KVM on hot inference path)
├─ AMD RAID LUNs / disk mount / BitLocker read access (root-only)
├─ host firewall / nspawn launch / cgroup-v2 resource policy
└─ systemd-nspawn factory-manager              ← FACTORY AUTHORITY START
   ├─ non-root UID mapping and private namespaces
   ├─ /dev/kvm ONLY (no nvme, RAID, DRI, libvirt system socket)
   ├─ allowed set of Factory-owned VHDX image files only
   ├─ per-user libvirt qemu:///session
   └─ ONE QEMU/KVM Factory guest
      ├─ tiny independent Linux supervisor root image
      ├─ guest nspawn: ephemerd
      │  └─ stock embedded containerd → OCI JIT jobs/Workbench
      ├─ guest nspawn: WSL distribution 1 → *original* ext4.vhdx
      ├─ guest nspawn: WSL distribution 2 → *original* ext4.vhdx
      └─ guest nspawn: WSL distribution N → *original* ext4.vhdx
```

### Exact authority boundary

1. **LinuxDev owner (physical host):** provisions/starts only the
   outer `factory-manager` system container and its host-enforced
   resource/security policy. Owns filesystem carrier unlock/NTFS
   visibility and mounts, RAID, EFI, boot, system-wide firewall and
   list of Factory-exposed image files. No routine Ephemerd or guest
   image update/synchronization responsibility.
2. **Factory management `nspawn`:** distinct user namespace, private
   mount/process/network space, AppArmor and restrictive host
   cgroup. Explicit bind of `/dev/kvm` plus device cgroup permission
   grants *that* container KVM use. Uses **libvirt `qemu:///session`**
   whose daemon and guest processes operate as the Factory non-root
   user. No connection to `qemu:///system` and no host libvirt socket.
   QEMU backing files and firmware live in this confined container's
   storage view; Factory can autonomously define/create/start/stop,
   reconfigure and repair its own QEMU VMs, with no privilege escalation
   to physical root. The authority is **not per-VM restricted** inside
   the Factory-owned account: the relevant restriction is the
   user/mount/device namespace and deliberately exposed storage.
3. **Factory common guest:** tiny independent Linux system/root image,
   not the original WSL2 root. Guest kernel/systemd own multiple
   separately named `nspawn` containers, one for each authorized
   WSL2 distro and **another for Ephemerd**. They share a **virtual
   kernel**, not a root filesystem, not UID/GID namespace, not
   packages or working state. Ordinary sibling mounts are not
   exposed to each other. The trusted Factory controller may
   still administer the guest and its mounted Factory-owned disks.
4. **Ephemerd:** guest-contained Linux service and embedded
   containerd/overlayfs/CNI. Nested OCI runs against the **VM guest
   kernel**, not the physical LinuxDev kernel. A privileged guest
   runtime would therefore endanger the **Factory guest** and its
   accessible disks, not gain host root merely through capabilities.
   Guest `nspawn` isolation is defense-in-depth; a guest
   kernel escape remains possible in principle. Candidate CI jobs
   have separate unprivileged caps, seccomp, restricted network and
   approved Factory Workbench isolation.
5. **Host kernel attack surface:** the Factory nspawn has explicit
   `/dev/kvm` access, which is a hardware-virtualization kernel ioctl
   attack surface. User namespaces/DAC do **not** make KVM exploits
   impossible; the trusted Factory controller is in scope, while
   untrusted candidate jobs are kept below the guest boundary.
   No raw NVMe, host /dev/dri, host KVM management sockets or
   private host paths. Do not promise "host totally inaccessible".

**Product evidence rather than invention:** an upstream systemd issue
documents an actual working `qemu-kvm` inside `nspawn` with bind-mounted
`/dev/kvm` and `DeviceAllow=/dev/kvm rw` (issue #38297).
Ubuntu/libvirt documents that `qemu:///session` runs daemon and guests
under the session user's DAC privileges, unlike root-controlled
`qemu:///system`. This proves the *individual mechanisms*. Their
combined hardening under this exact Ubuntu/ASUS configuration is
still an acceptance requirement; do not invent completed E2E results.

### Multiple independent WSL2 images, without re-provisioning

Each WSL2 system owns exactly **one canonical root `ext4.vhdx`**
plus any separate durable data image (e.g. Factory Btrfs volume).
The KVM guest receives them **directly as QEMU virtio block disks**
using the VHDX format; `qemu-nbd` is not required for that image's
guest-side presentation. Guest kernel mounts its ext4 tree at a unique
system-container root path; `systemd-nspawn` launches that particular
distro with its original OS users, packages, UID/GID and state. Its
installed kernel, bootloader or Windows WSL launcher are not assumed
to reside inside the VHDX. The guest supervisor OS and kernel are
separate from all WSL roots.

The shared-VHDX contract is still **exclusive one-writer**, not shared
access: on Windows, WSL2 owns it; on native Linux, Factory QEMU owns it.
All guest nspawn services must shut down; every attached filesystem
unmount, guest powerdown, QEMU disk close, NTFS flush and Windows
clean shutdown must happen before changing the owning host.
No `wsl --export`, clone synchronization or on-disk ownership
conversion for routine switches. Guest idmapped nspawn root mounts
where required must preserve numeric WSL UID/GID; automatic recursive
chown fallback is prohibited.

Factory can register multiple authorized WSL distributions and
manage each independently within the common guest (start/stop,
packages, lifecycle, separate data paths). Some WSL roots may be
operator-owned rather than Factory-owned. They are **not** offered
to Factory management without a distinct trust/authorization decision.
Anyone with Factory management authority can read/write permitted
VHDX images via QEMU; sibling namespace isolation is NOT a secrecy
boundary against that administrator.

### No privileged host updater or control socket

The Factory manager is not a host service with LinuxDev root power.
It *can* update, repair or replace guest root, guest controllers,
nspawn configs, Ephemerd, OCI images and running WSL services by
direct libvirt session management, guest SSH/console and stock
guest systemd. Repair access exists even if Ephemerd service and CI
are entirely stopped. The host does not install a custom syncd,
repair proxy or per-image updater. Host responsibilities remain
generic device/isolation/physical OS lifecycle only.

**Outbound guest network:** session-libvirt's documented
per-user mode uses user-mode networking, not system libvirt NAT
bridges. Do not expose host/private LAN/VPN access by assuming
NAT is a security boundary. Host-owned network filtering and
nspawn-visible networking restrict allowed destinations; guest
CNI firewalls separately restrict hostile JIT jobs. Management
transport is guest-internal console/virtio-serial or confined
management network, not an arbitrary host control socket.

### Elastic memory and minimum footprint

The host owns the **single 64 GB UMA allocator** and direct
Radeon/ROCm inference. QEMU/VM memory is *demand-paged* and
limited by the host's cgroup-v2 pressure policy, not allocated as
a permanently resident fixed partition. Use stock
**virtio-balloon free-page reporting**, which returns pages that
the guest has truly freed, and conventional ballooning/reclaim
capabilities; QEMU's guest-visible maximum is only an upper bound.

- LinuxDev uses systemd slice priorities with `MemoryLow` protection
  for GUI/active inference, `MemoryHigh` soft reclaim for background
  Factory pressure, and host `zswap` backed by encrypted native
  NVMe swap where the finalized physical layout allows it.
- The guest also runs cgroup-v2 to manage individual WSL distros
  and Ephemerd independently, with guest swap policy. Owner can
  suspend lower-priority workloads before huge models when
  reclaim alone is insufficient.
- Caveat: free-page reporting does **not** automatically reclaim
  guest page cache, and host anonymous-swap reclamation is not
  equivalent to a no-latency memory hot-unplug. GPU-pinned
  memory cannot be assumed pageable. Do not disable host swap,
  use preallocated/locked hugepages or promise the complete
  64 GB is usable by one model.
- Avoid an elaborate self-authored RAM balancing daemon. Measure
  RSS/PSS, guest cache retention, host PSI, swap I/O, effective
  model throughput and guest QoS under real concurrency.

### Source evidence

- Actual KVM in nspawn with `/dev/kvm` bound: https://github.com/systemd/systemd/issues/38297
- Ubuntu libvirt unprivileged `qemu:///session`: https://ubuntu.com/server/docs/how-to/virtualisation/libvirt/
- QEMU process privilege separation: https://www.qemu.org/docs/master/system/security.html
- QEMU free-page reporting: https://wiki.archlinux.org/title/QEMU
- WSL VHDX canonical ownership: https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk
- Libvirt URI/permissions: https://libvirt.org/drvqemu.html
- systemd-nspawn nested system containers: https://man7.org/linux/man-pages/man1/systemd-nspawn.1.html
- Ephemerd Linux embedded containerd:
  https://github.com/ephpm/ephemerd/blob/main/docs/architecture/embedded-containerd.md

## GPU / local inference — native, memory-aware

Target: **Ryzen AI Max+ 392 / Radeon 8060S (gfx1151 family)** on ASUS FA401EA.
ASUS advertises up to **64 GB total unified memory**, distinct from **128 GB**
Max+ 395 examples on Framework Desktop and other machines. Therefore an AMD
example reaching **120 GB GTT** on a 128 GB machine **must not** be restated as
a target on this ASUS.

- Linux amdgpu/TTM GTT allocation and tuned kernel limits can enable
  substantially larger GPU-visible memory allocations than common Windows
  configurations. AMD publishes a 120 GB GTT recipe for a different 128 GB
  Ryzen AI Max+ 395 system; GTT is **not** the same as physically separate VRAM.
- The inference executor should use the host's AMD driver and a suitable native
  ROCm/HIP or Vulkan backend, without a full GPU VM. `llama.cpp` on gfx1151 is
  a high-priority supported-ecosystem candidate; the exact backend, quantization,
  memory limits and model mix remain unselected.
- AMD ROCm support matrices are **GPU SKU, distribution, ROCm and framework
  version-specific**. Matrices listing 395/390/385, for example, do **not**
  automatically certify the 392 SKU even when the graphics architecture matches.
  Ubuntu 26.04 LTS with its in-tree amdgpu/kernel 7.0 and distro ROCm CI
  is the documented **leading host selection**; validation of the full
  FA401EA hardware and its RAID/boot topology remains a release gate.
- GPU memory has to leave usable headroom for host GUI, processes, Ephemerd
  and child environments, including the shared namespace-based Factory child;
  assess actual
  loaded model+KV cache, speed and memory pressure rather than a BIOS/driver
  allocation label.

Sources:
- ASUS target: https://www.asus.com/de/laptops/for-gaming/tuf-gaming/asus-tuf-gaming-a14-2026-fa401ea/
- AMD technical memory demonstration:
  https://www.amd.com/en/developer/resources/technical-articles/2026/how-to-run-a-one-trillion-parameter-llm-locally-an-amd.html
- AMD ROCm Linux Ryzen compatibility:
  https://rocm.docs.amd.com/projects/radeon-ryzen/en/docs-7.2.1/docs/compatibility/compatibilityryz/native_linux/native_linux_compatibility.html
- AMD llama.cpp ROCm:
  https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/inference/llamacpp.html

## Updated host platform research: 2026-10-17

**Lead product selection: Ubuntu 26.04 LTS Desktop, stock GNOME session.**
This is justified by the actual host hardware, not by Factory implementation
languages or development dependencies:

- AMD **ROCm 7.14.1** compatibility matrix groups **Radeon 8060S** with the
  **Ryzen AI Max 300 Series, gfx1151**, and identifies **Ubuntu 26.04
  (GA Linux 7.0)** with in-distribution GPU kernel driver. The older ROCm
  7.2 documentation listing particular APUs but not `Max+ 392` is no longer
  the strongest applicable hardware support statement; 8060S/gfx1151 is
  explicitly covered in the newer matrix.
- Canonical packages ROCm 7.1.0 through Ubuntu Universe and actually CI-tests
  `gfx1151` (Radeon 8040S/8050S/8060S), with llama.cpp, PyTorch and
  Lemonade integration tests. The distro packages are an economical default
  inference starting point. Do **not** imply they are the same version as
  AMD's ROCm 7.14.1 matrix.
- `llama.cpp` + gfx1151 ROCm/HIP is the lead local inference product.
  `llama-server` is a host service consuming the device directly; Vulkan
  is a documented fallback/comparison, not another mandatory stack.
  Model execution must be judged by actual weights+KV+concurrent working
  memory and stable tokens/s, **not** by a large GTT or VRAM number alone.
- Default desktop can remain stock GNOME. A second desktop and a host-root
  Factory SDK have no demonstrated economic benefit.

Sources:
- https://rocm.docs.amd.com/en/docs-7.14.1/compatibility/compatibility-matrix.html
- https://documentation.ubuntu.com/release-notes/26.04/changes-since-previous-interim/
- https://rocm.docs.amd.com/en/docs-7.2.0/how-to/system-optimization/strixhalo.html

### Established AMD Linux RAID product line — evidence correction (2026-10-17)

The earlier assertion that RAIDXpert2 had only an experimental community
Linux driver was **wrong**. AMD maintains vendor Linux `rcraid`
drivers and documented installation/SDK update flows:
- AMD publicly distributes Linux RAID driver 9.3.0.00276 for
  Ubuntu 20.04, and AMD RAID Ubuntu guide revision 1.01 (2025)
  documents 9.3.2/9.3.3 drivers, DKMS, driver_sdk and kernel
  upgrades, including signed/MOK workflows.
- Lenovo publishes an official OEM **AMD Software Based RAID Linux
  Utility 9.3.3** dated 2025-11-19 for Ubuntu 24/RHEL9. Its
  *description says Utility*; inspecting that package's actual
  kernel-driver payload is required before claiming it installs a
  driver compatible with the ASUS. This supports continued OEM
  maintenance; not proof for Ubuntu 26.04.
- AMD Windows driver 9.3.3.00291 (2026) explicitly includes the
  AMD Ryzen AI Max 300 family; this describes a **Windows driver**
  and says nothing automatic about the matching Linux kernel module.
- The community reimplementation has real TRX50 evidence but
  is **not first choice** over the vendor product line.

**Specific residual integration evidence:** identify the real ASUS
RAID PCI ID and existing multiple-single-NVMe LUN layout, and
check vendor driver/SDK 9.3.3 compatibility against the selected
Ubuntu 26.04 kernel, Secure Boot module signature and boot-time
LUN enumeration. Kernel updates must not strand the root FS.
The vendor-supported Ubuntu 24 package does not yet establish
Ubuntu 26.04 support on the physical ASUS.

Links:
- https://www.amd.com/en/support/downloads/drivers.html/chipsets/strx4/trx40.html
- https://docs.amd.com/api/khub/documents/l_VvImC0IX9mjsLPOPymFw/content
- https://support.lenovo.com/us/en/downloads/ds578298-amd-software-based-raid-linux-utility
- https://www.amd.com/en/support/downloads/drivers.html/chipsets/am5/x870.html

### Physical ASUS storage — a newly discovered binding prerequisite

**Physical reality, established in Windows issue #9:** the second SSD is not
currently an ordinary partitionable native NVMe device from WinOps' point of
view. The **Lexar NM790 4TB** is presented as an **AMD RAIDXpert2 virtual LUN**
(WinOps C: observed on `AMD-RAID Array 2`, with its own ESP and WinRE).
The Windows installation needed boot-critical `rcbottom → rcraid → rccfg`
drivers. SSD1 retains separate Windows Home. This is *observed on the ASUS*,
not only a proposed Windows architecture or VirtualBox assumption.

The earlier shared-NTFS/dynamic-VHDX analysis answers the capacity and
filesystem-interoperability design. It does **not** prove the lower-level
RAIDXpert2 virtual LUN is safely visible to Ubuntu.

Evidence on 2026-10-17:
- AMD's March 2025 Ubuntu RAID Quick Start Guide explicitly lists supported
  Ryzen 7000/Threadripper, B650/X670/TRX chipsets, etc.; that list is not
  affirmative native Ubuntu 26.04 support for the **actual ASUS AMD RAID
  controller and existing multi-LUN layout**. CPU SKU alone is not a
  discriminator. It documents an external RAID driver, not automatic
  upstream kernel support.
- Community `joeytroy/amd-raid-driver` exposes GPL reverse-engineered `rcraid`,
  claims Ryzen AI Max chipset coverage and Linux 7.0 compatibility and has
  real two-NVMe RAID0/RAID1 boot evidence **on TRX50**, not on this ASUS with
  potentially multiple LUNs on a single NVMe. It is an interesting research
  candidate, **not a production acceptance**. Its self-described unsigned
  module needs a Secure Boot signing/key management path (or disabling SB),
  and it explicitly warns that raw physical NVMe devices can look like RAID
  members. Never run its default install script blindly on production storage.
- Older `rcraid-dkms` projects themselves warn about weak AMD Linux support.
  Assuming stock `mdadm` can import AMD RAIDXpert2 metadata as Intel IMSM
  would be unsupported.

**Safety gate:** Prefer the supported vendor Linux RAID driver line,
not reverse engineering. Do not offer the Linux installer the raw NM790
4TB as an empty target. Do not change AMD RAID firmware settings, WinOps LUN allocation or
SSD1 until native safe access is established with exact array identity and
independent recovery. A distinct Linux root on a genuinely accessible
non-member partition/disk may be investigated as an alternative, but neither
its capacity nor independent boot on *this* RAID-mode ASUS has been established.
Observe first; decide from evidence; do not turn a working WinOps into a test
fixture.

Sources:
- Physical ASUS baseline: https://github.com/evanmih-cmd/linux/issues/9#issuecomment-6110011694
- AMD Ubuntu RAID guide (March 2025):
  https://docs.amd.com/api/khub/documents/l_VvImC0IX9mjsLPOPymFw/content
- Community driver: https://github.com/joeytroy/amd-raid-driver
- Older DKMS packaging: https://github.com/thopiekar/rcraid-dkms

**Active work tracker:** https://github.com/evanmih-cmd/linux/issues/17
**Execution plan:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## What should determine the host distribution

Only host capabilities: graphics/Wayland input-display ergonomics, AMD GPU
driver/kernel/ROCm compatibility, reliable container/VM/volume access,
ephemerd Linux runtime, updates/recovery, and low administration cost.

Languages, frameworks, Factory agents, build images and per-project dependencies
belong to child environments; they must not be used as arguments for distro
selection unless they prove a **host-specific, unavoidable dependency**.

## Release-oriented next steps

1. Reuse the prior **NTFS dynamic-VHDX shared AI data pool** analysis instead
   of re-running product selection. Resolve only the additional compatibility
   of the **original existing WSL2 distro ext4.vhdx** as a native-Linux child
   (including non-image Factory state, safe two-way updates, and host-specific
   integrations), plus reconcile the storage placement with current disks.
2. Use Ubuntu 26.04 LTS Desktop + stock amdgpu as the working baseline,
   with packaged ROCm first and newer pinned AMD ROCm only where necessary;
   validate exact ASUS peripherals, resume and graphical session.
3. Use one host-bound **Factory manager nspawn** with `/dev/kvm` and
   `libvirt qemu:///session`, managing **one common KVM guest** with
   multiple distinct guest-side WSL nspawn environments and a separate
   Ephemerd nspawn. No privileged physical-host updater; verify host
   cgroups/ballooning/zswap/swap priorities under LLM load.
4. Set functional acceptance criteria using actual existing environment
   continuity, representative Ephemerd job execution, and real >48 GB LLM
   usable-memory operation, plus a fully usable graphical session.
5. Only after evidence-backed architecture selection, plan LinuxDev
   installation and provisioning without disrupting Windows.
