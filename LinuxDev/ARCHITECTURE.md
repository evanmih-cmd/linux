# LinuxDev — host architecture research

**Status: research / unapproved implementation decisions, 2026-10-17.**
Business authority: [BUSINESS_REQUIREMENTS.md](BUSINESS_REQUIREMENTS.md).

## Boundaries

```text
                  ASUS TUF A14 FA401EA
                      native LinuxDev
              ┌─────────────────────────┐
              │ Graphical Linux desktop │
              │ Host lifecycle/security │
              ├───────────┬─────────────┤
              │ Child envs│ Native LLMs │
              │ Factory   │ 8060S / UMA │
              │ projects  │ ROCm/Vulkan │
              │ existing  │             │
              │ WSL2 FS   │             │
              ├───────────┴─────────────┤
              │ systemd-nspawn (lead)   │
              │ ┌───────────────────┐  │
              │ │ Original WSL2 FS  │  │
              │ │ Factory control   │  │
              │ │ Ephemerd + OCI    │  │
              │ └───────────────────┘  │
              └─────────────────────────┘

Windows WSL2 <— exclusive ownership of persistent ext4.vhdx —> LinuxDev
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
Linux:   QEMU VHDX block layer → ext4 mount → nspawn child OS
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

## Unified Factory child: namespace-first and memory-elastic

**Updated research direction, 2026-10-17:** The owner prefers no preallocated
guest RAM. **First candidate** is **one systemd-nspawn system container**
hosting the canonical *original* Factory WSL2 filesystem **and** Linux
Ephemerd with its embedded containerd/OCI. There is no separate Ephemerd
VM, and VHDX by itself does not require a VM. This is a leading hypothesis
**conditional on a real nested-containerd and security proof**, not an
already accepted LinuxDev release.

### Host topology, one physical kernel

```text
Windows booted                              LinuxDev booted
  WSL2 VM                                     Ubuntu Desktop
     |                                         GPU + ROCm/LLM
original WSL2 ext4.vhdx                            |
     |   (EXCLUSIVE, time-alternating RW)      NTFS -> qemu-nbd
     +---------------------------------------------+
                                                   |
                                            systemd-nspawn
                                            (Factory user namespace)
                                               | original WSL OS tree
                                               | trusted Factory control
                                               | Ephemerd Linux service
                                               | embedded containerd
                                               +-- isolated OCI jobs
```

The LinuxDev host owns only the supported VHDX mount/attach/unmount
lifecycle, nspawn service/machine lifecycle, kernel isolation policy and
host RAM/swap. It is NOT a bespoke updater. The independent trusted
Factory controller in the Factory system container can use in-child
systemd/admin privileges to repair/upgrade Ephemerd when Ephemerd itself
is broken or stopped. Untrusted CI jobs get no controller credentials
or privileged direct embedded-containerd access.

**Container guardrails (all required, not magic feature names):**
- Distinct, non-identity `--private-users=pick` UID/GID mapping with
  `--private-users-ownership=map` (idmapped mount), **never `chown` or
  `auto` fallback to recursive `chown`**: the same WSL2 ext4.vhdx must
  keep original numeric UID/GID ownership across Windows/Linux boots.
  If mapping is unavailable for the real mount path, this candidate
  **fails closed**, rather than silently rewriting WSL filesystem metadata.
- Isolated mount/PID/network/IPC namespaces, minimal delegated capabilities
  and seccomp, host-enforced AppArmor profile, private devices and
  read-only/no-bind exposure of LinuxDev/Windows operator storage, secrets,
  RAID and libvirt sockets. Factory root must be root **only in its user
  namespace**, not initial host namespace; ordinary CI jobs are further
  isolated and less privileged.
- Private veth/bridge with host firewall denying host, LAN and VPN access
  except explicitly required Factory control and allowed GitHub/registry
  egress. Do not assume `--private-network` alone gives working OCI CNI
  or protects local host services.
- cgroup-v2 delegation is narrowly scoped. Nested containerd/runc requires
  actual mount, overlayfs, CNI/iptables/netfilter, namespaces, cgroup and
  AppArmor behavior to be proven under this user namespace; **do not**
  hand the nspawn child broad host `CAP_SYS_ADMIN`, `CAP_NET_ADMIN`,
  `--privileged` or a host Docker/containerd socket as a workaround.

**Concrete upstream blocker to qualify:** Ephemerd Linux embeds a complete
containerd server and uses runc, overlayfs and CNI with iptables. Its job
AppArmor layer is documented as **best-effort**: if profile installation
fails, jobs can proceed without that layer. Nested userns/container
AppArmor support must therefore be inspected and negatively tested
explicitly, never inferred from "ephemerd supports Linux". Its own
`[dind].allow_privileged=false` remains necessary but insufficient to
prove the outer host boundary.

The Ubuntu **26.04 systemd-container package is from systemd 259.5**,
whereas newer systemd **260** userns `--private-users-delegate=`
enhancements must NOT be assumed available. If the existing product
cannot support the required nested userns/cgroup features without unsafe
host privilege, reject namespace-only Ephemerd containment and use the
KVM fallback. No bespoke host reimplementation of Ephemerd or 260-only
patching by default.

### Shared elastic memory: OS scheduling, not VM partitioning

The **physical** 64 GB is one CPU/iGPU UMA pool. Factory child, GUI, LLM
and Ephemerd allocate memory **on demand** from the same Linux allocator.
No RAM block is reserved for an idle system container.

- **cgroup v2** and stock systemd slices control reclaim priority:
  `MemoryLow=` gives best-effort protection to operator desktop and
  active native LLM cgroups; use `MemoryMin=` only for a narrow host
  survival floor. Do not assign a fake fixed minimum to all processes.
- Factory/background container groups have weaker protection; `MemoryHigh=`
  is a **soft throttle/reclaim ceiling** when it is justified and should
  not be confused with preallocation. `MemoryMax=` is a final runaway
  guard, not the primary RAM-distribution mechanism. It may remain
  unset for ordinary elastic work when no useful cap is demonstrated.
  `MemorySwapMax=` can enforce swap ceilings where relevant.
- The kernel reclaims cache and pageable anonymous memory by priority.
  **zswap with real native-Linux NVMe-backed swap** is a leading
  economical mechanism: compressed cold pages stay in a *dynamic*
  cache first, with writeback to a real swap device/file when needed.
  zram-only swap holds compressed pages in RAM and by itself is not
  a substitute for disk-backed overcommit. Exact swap location,
  encryption and capacity must respect RAID/Windows data safety; do
  not put a writeable swapfile on a hibernated NTFS or VHDX carrier.
- Stock **systemd-oomd / PSI** catches sustained memory pressure and
  selects eligible lower-priority units for termination when reclaim
  and swapping are insufficient. It is NOT a memory allocator or
  a guarantee that no process will be OOM-killed. Configure control
  groups so a CI workload does not drag down the desktop session.
- LLM model weights/KV cache and especially GPU mappings may be pinned
  or otherwise non-pageable; swap is for pageable **background CPU
  process memory**, not a way to fit arbitrarily large GPUs in RAM.
  Measure real concurrency and recovered RAM, stalls/PSI, NVMe I/O,
  OOM outcomes and token throughput without made-up memory numbers.
  Activating a huge model may still require pausing/killing Factory
  jobs, but **not** stopping a VM merely to reclaim its idle reservation.

The host's memory priority policy belongs to LinuxDev, never to a
guest-controlled global `/sys/fs/cgroup` or kernel tunables. Factory
may tune its **delegated inner cgroups only**, if supported.

### VM fallback without a false fixed-RAM dichotomy

If the userns+nested containerd configuration requires dangerous
permissions, the fallback is **one** KVM/libvirt Factory guest sharing
the same original VHDX root and in-guest Ephemerd; no second VM for
the daemon. KVM can also support guest memory **ballooning /
virtio-mem**, so it does not inherently require forever reserving an
entire declared maximum in resident host RAM. However the extra guest
kernel/page caches, cooperation of a balloon driver, dual host/guest
swap and recovery latency add operational overhead and make global
priority control less transparent than native cgroups. No claim that
all guest RAM can always be returned on demand. The VM is selected on
measured isolation/runtime grounds, NOT on a fictitious static-RAM
requirement.

### Cross-Windows simplification

After acceptance on Linux, evaluate running Ephemerd's Linux backend
from the **same** original Factory WSL2 distribution under Windows,
retiring the present privileged Windows-host service/updater.
This is a separate conditional migration: kernel/containerd/CNI,
app-service permissions, bootstrap and autonomous WSL lifetime must
be proven. Microsoft cautions that mere systemd services do not
keep WSL alive. Do not disable today's working service prematurely.

### Required product discrimination before declaring acceptance

Use a **disposable copy** of a representative WSL image, never the only
running Factory filesystem. Prove that nspawn starts the original distro,
normal user identity is preserved without on-disk `chown`, Linux
Ephemerd v0.2.20 runs its embedded containerd/BuildKit and real jobs,
nested OCI works without initial-host-namespace privilege, AppArmor
and outer restrictions actually enforce, guest/root cannot write
LinuxDev host/Windows storage or change host firewall, and the
independent Factory controller repairs Ephemerd when it is stopped.

Then measure concurrent GUI + real native >48 GB inference +
background Factory jobs: prove cold pages are reclaimed/swapped,
interactive latency is acceptable, and model allocations/active
jobs survive or fail with predictable priority under memory pressure.
Finally do an **exclusive-owner WSL2 roundtrip** using the *real*
original VHDX only after the disposable route is accepted.

**Sources**
- systemd-nspawn userns/idmapped ownership:
  https://manpages.ubuntu.com/manpages/resolute/man1/systemd-nspawn.1.html
- Ubuntu 26.04 systemd-container 259.5:
  https://packages.ubuntu.com/resolute/systemd-container
- Kernel cgroup-v2 limits / reclaim:
  https://docs.kernel.org/admin-guide/cgroup-v2.html
- systemd cgroup resource controls:
  https://man7.org/linux/man-pages/man5/systemd.resource-control.5.html
- Kernel zswap: https://docs.kernel.org/admin-guide/mm/zswap.html
- Ephemerd embedded containerd:
  https://github.com/ephpm/ephemerd/blob/main/docs/architecture/embedded-containerd.md
- Ephemerd security and AppArmor best-effort fallback:
  https://github.com/ephpm/ephemerd/blob/main/docs/guides/security.md
- Ephemerd Linux CNI bridge:
  https://github.com/ephpm/ephemerd/blob/main/pkg/networking/network_linux.go
- QEMU/KVM memory hotplug alternative:
  https://virtio-mem.gitlab.io/user-guide/user-guide-libvirt.html

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

**Safety gate:** Do not offer the Linux installer the raw NM790 4TB as an empty
target. Do not change AMD RAID firmware settings, WinOps LUN allocation or
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
3. Prove **one nspawn Factory system container** for the original WSL root
   and embedded-containerd Ephemerd under strict user namespaces/host
   confinement, plus elastic cgroups-v2/zswap/host swap under LLM
   pressure. Keep **one common KVM guest** only as a warranted isolation
   fallback. Factory administration must never become host administration.
4. Set functional acceptance criteria using actual existing environment
   continuity, representative Ephemerd job execution, and real >48 GB LLM
   usable-memory operation, plus a fully usable graphical session.
5. Only after evidence-backed architecture selection, plan LinuxDev
   installation and provisioning without disrupting Windows.
