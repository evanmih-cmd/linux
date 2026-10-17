# LinuxDev — Linux host for Factory and local LLMs

**Status:** Product scope confirmed 2026-10-17; implementation architecture under research.
This workstream is independent of `../windows/` and `../portable/`; their OS,
encryption, provisioning and mobility choices are not implicitly inherited.

## What LinuxDev is

LinuxDev is a **native Linux host**, not the place where application development
dependencies or Factory's internal architecture should be installed.

It has exactly three product roles:

1. **Host child environments.** Run Factory and its child projects inside their
   own persistent Linux environments. Existing **Windows WSL2 distributions
   must also run on LinuxDev unchanged as working environments**: edits and
   generated state made on Linux must remain available when returning to
   Windows WSL2, and vice versa.
2. **Provide a convenient graphical desktop** for the human operator.
3. **Execute demanding local workloads directly**, primarily GPU-accelerated
   LLM inference, without unnecessary virtualization or GPU mediation.
   
**Ephemerd** runs in Factory's own execution boundary, never as a
privileged service on the physical LinuxDev root. **Selected composition:**

- One **host-owned systemd-nspawn** management domain (`factory-manager`)
  grants Factory an explicitly bounded authority surface: its own
  `/dev/kvm` and **libvirt `qemu:///session`** as an unprivileged session.
  Neither `qemu:///system` nor a host privileged management socket is shared.
- Factory controls **one shared, minimal Linux KVM guest**, not one VM
  per WSL distro. Inside it, **separate systemd-nspawn containers** run
  each original WSL2 distribution, plus a **separate Ephemerd domain**.
  More than one WSL distro is supported; no distro is designated as the
  canonical replacement for the others.
- All WSL2 environments keep their **own** original `ext4.vhdx` and other
  persistent disks, with only one writable owner across Windows/Linux.
- RAM is elastic: host cgroup v2 + host zswap/NVMe swap + QEMU
  virtio-balloon free-page reporting. An advertised VM maximum is not
  a permanently occupied amount of physical RAM.

This is the **chosen architecture**, not a claim that ASUS storage or the
original multiple-WLS distro migration has passed a physical acceptance
test. Details: [FINAL_DESIGN.md](FINAL_DESIGN.md).

Workloads inside Factory determine the requirements of their child environments,
**not the distro, application stack, or daily desktop software of LinuxDev**.
The host choice is driven by reliable child-environment execution, ergonomics and
native AMD GPU/UMA driver support.

## Current target

- Physical target: existing **ASUS TUF A14 FA401EA**, AMD **Ryzen AI Max+ 392**
  with Radeon **8060S**. ASUS advertises **up to 64 GB unified RAM** for this
  model, not the 128 GB used in some Max+ 395 demonstrations.
- Windows remains a working alternative; switching to LinuxDev must not
  destroy existing Windows and WSL2 systems.
- Windows' current **48 GB graphics-memory limitation** motivates testing
  native Linux memory management for larger LLMs. This is an optimization goal,
  not proof that the full 64 GB can become usable model memory.

## Documents

- [Execution plan and evidence gates](IMPLEMENTATION_PLAN.md) — the concrete
  2026-10-17 host choice, live ASUS RAID blocker, and release sequence
  tracked in [issue #17](https://github.com/evanmih-cmd/linux/issues/17).

- [Business requirements](BUSINESS_REQUIREMENTS.md) — confirmed needs, independent
  of technical mechanism.
- [Architecture research](ARCHITECTURE.md) — proposed seams and evidence,
  with a clear distinction between established product capabilities and
  the remaining interoperability questions.

## Decisions already made

- Native Linux OS host with a graphical desktop.
- Factory runs in child entities; the host is **not** tailored to the internals
  of Factory or individual child projects.
- Existing WSL2 working environments must continue across Linux/Windows
  transitions, preserving changes in both directions.
- Factory must be able to administer its own QEMU virtual machines and
  in-VM Ephemerd/WSL environments **without LinuxDev root authority** or a
  bespoke trusted host updater. Each WSL distro is independent and persistent.
- Local LLM inference uses the physical GPU and shared memory as directly and
  efficiently as practical.
- Product First / Economy First: favor supported products, minimize lifetime
  engineering and operational burden, introduce glue only for a proven gap.

## Still open (do not silently decide)

- Physical Ubuntu 26.04 RAID/boot integration and the exact gfx1151 runtime
  outcome on this ASUS; Ubuntu 26.04/GNOME is the selected baseline.
- Exact **zero-copy, bidirectional WSL2 image ownership** and its storage
  placement/unlock across OSes, including crash consistency.
- How WSL-specific host integrations and existing Factory runner services map
  to Linux containers or another compatible runtime.
- Qualified delegated `factory-manager` nspawn -> unprivileged libvirt
  `qemu:///session` -> common VM -> **multiple separate WSL nspawn
  containers** and separate Ephemerd nspawn; exact permission, memory,
  network and cross-OS VHDX acceptance still to be demonstrated on the
  device. No separate Ephemerd VM.
- Native inference backend and realistic maximum model weights+KV-cache size
  without exhausting memory needed by host/child workloads.
- Host installation and rollback strategy that leaves Windows recoverable.

No partitioning, OS reinstall, package baseline, new VMs or guest migrations
are authorized by this concept draft.
