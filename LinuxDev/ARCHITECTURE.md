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
              │ ephemerd (Linux)        │
              │ embedded containerd/OCI │
              └─────────────────────────┘

Windows WSL2 <— exclusive ownership of persistent ext4.vhdx —> LinuxDev
```

No Factory compiler, build tool, agent framework or project-specific SDK belongs
in the host root filesystem merely because a child uses it. Host components
are limited to desktop, platform drivers, guest/container runtime, storage,
recovery and native LLM execution.

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
- VHDX physical placement and mount accessibility from BOTH operating systems;
  BitLocker-encrypted NTFS volumes cannot simply be assumed writable from Linux
  without a supported unlock procedure.
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

## Ephemerd — direct Linux backend

Factory currently pins **ephemerd v0.2.20** in
`evanmih-cmd/factory:infra/ephemerd/windows/settings.json`. Its Windows
bootstrap uses a Windows service and HCS/Hyper-V Linux VM with a VHDX.

Upstream ephemerd also supports **native Linux**, with embedded containerd and
OCI job containers directly on the Linux host, systemd service integration and
Linux runner images. The existing Factory runner image configuration names
`ghcr.io/evanmih-cmd/factory-github-runner:production` and permits DIND via
ephemerd's fake Docker API. These are Factory-owned contracts, not LinuxDev
developer tools.

Proposed LinuxDev role:
- run ephemerd as a controlled Linux host service;
- use the Linux containerd backend rather than reproducing Windows HCS VM;
- bind Factory dispatch/image/credentials to an appropriate Linux configuration;
- preserve Factory's trust separation, avoid exposing host/Windows secrets,
  and explicitly assess **container shared-kernel isolation vs Hyper-V VM
  isolation** before accepting untrusted workflow execution.

The upstream existence of the Linux backend does **not** constitute acceptance
of Factory's exact v0.2.20 configuration on the target host.

Sources:
- https://github.com/ephpm/ephemerd
- https://github.com/ephpm/ephemerd/security
- https://github.com/evanmih-cmd/factory/blob/main/infra/ephemerd/config.toml
- https://github.com/evanmih-cmd/factory/blob/main/infra/ephemerd/windows/settings.json

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
  Ubuntu 24.04.x has documented AMD support and is an important **candidate**;
  no LinuxDev distribution has yet been accepted.
- GPU memory has to leave usable headroom for host GUI, processes, Ephemerd
  and child environments; assess actual loaded model+KV cache, speed and memory
  pressure rather than a BIOS/driver allocation label.

Sources:
- ASUS target: https://www.asus.com/de/laptops/for-gaming/tuf-gaming/asus-tuf-gaming-a14-2026-fa401ea/
- AMD technical memory demonstration:
  https://www.amd.com/en/developer/resources/technical-articles/2026/how-to-run-a-one-trillion-parameter-llm-locally-an-amd.html
- AMD ROCm Linux Ryzen compatibility:
  https://rocm.docs.amd.com/projects/radeon-ryzen/en/docs-7.2.1/docs/compatibility/compatibilityryz/native_linux/native_linux_compatibility.html
- AMD llama.cpp ROCm:
  https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/inference/llamacpp.html

## What should determine the host distribution

Only host capabilities: graphics/Wayland input-display ergonomics, AMD GPU
driver/kernel/ROCm compatibility, reliable container/VM/volume access,
ephemerd Linux runtime, updates/recovery, and low administration cost.

Languages, frameworks, Factory agents, build images and per-project dependencies
belong to child environments; they must not be used as arguments for distro
selection unless they prove a **host-specific, unavoidable dependency**.

## Release-oriented next steps

1. Determine a credible storage topology and native Linux runtime for the
   *existing* WSL2 VHDX images, including safe two-way state and non-image
   Factory volumes/dependencies.
2. Select a native Linux kernel/distro/desktop based on the exact ASUS GPU and
   current ROCm and inference backend interoperability, not personal distro
   preference.
3. Map Factory's pinned ephemerd version/config to the Linux backend and
   explicitly assess Linux container security/isolation.
4. Set functional acceptance criteria using actual existing environment
   continuity, representative Ephemerd job execution, and real >48 GB LLM
   usable-memory operation, plus a fully usable graphical session.
5. Only after evidence-backed architecture selection, plan LinuxDev
   installation and provisioning without disrupting Windows.
