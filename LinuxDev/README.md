# LinuxDev — Linux development environment

> **Status: concept draft, 2026-10-17.** This is a new, independent design
> workstream. Nothing in this document authorizes installation, partition
> changes, hardware purchases, or changes to the existing workstations.
> Candidate solutions below are **not** accepted architectural decisions.

## Purpose

Design a practical environment for **development targeting Linux**.
The initial working interpretation of "LinuxDev" is a developer workstation or
development environment, **not** a rename of the existing portable sensitive-workload
Linux and **not** an extension of the Windows credential workstation.
The exact workloads and deployment target remain to be established.

## Position within this repository

- [`../windows/`](../windows/) — the Windows 11 Pro security/identity
  workstation. Its business requirements remain authoritative **there**.
- [`../portable/`](../portable/) — the frozen portable Linux
  sensitive-workload design/research record. Its portability, encryption,
  TPM/PIN and installation decisions are **not inherited** by LinuxDev.
- **`LinuxDev/`** — a separate set of requirements and architecture decisions,
  to be formulated for development workloads.

The three environments can share research or proven implementations, but
sharing a repository does not imply sharing a security boundary, machine,
disk layout, boot chain, update policy, or deployment method.

## Decision principles

1. **Product First:** use an established and supported capability before
   engineering a substitute. Custom work is allowed when its benefit is proven.
2. **Economy First:** optimize total lifecycle cost, including daily friction,
   recovery, update overhead, hardware cost, maintenance and engineering effort.
3. **Workload first:** choose an environment by the required development
   capabilities; don't choose a distribution or installer first and retrofit
   the use case to it.
4. **Reproducibility:** prefer declarative, documented provisioning of the
   development toolchain and workspace; avoid artisanal post-install steps.
5. **Isolation proportional to the threat:** compilation, package execution,
   dependencies, containers and AI-generated code can be untrusted. Determine
   the necessary isolation **from the workloads** instead of assuming either
   full trust or mandatory air-gapping.
6. **Protection of current systems:** no proposal may casually modify the
   existing WinOps/Windows Home installations or their boot and recovery paths.
7. **Evidence rather than attractive diagrams:** assess specific current
   product/version and hardware support before claiming a candidate works.

## Questions to settle before selecting an architecture

| Dimension | Required information | Current status |
| --- | --- | --- |
| Main activities | Application development, infrastructure, containers, kernel/drivers, desktop/UI, AI/ML, or other? | Open |
| Linux fidelity | Is Linux userspace sufficient, or is a complete Linux kernel, native boot, GUI, USB, PCIe/GPU or hardware testing needed? | Open |
| Execution location | Existing ASUS, another machine, virtual machine, cloud/remote host, removable media? | Open |
| Windows relationship | Must Windows and LinuxDev run concurrently? What data/services may be shared with WinOps? | Open |
| Toolchains | Languages, compilers, build systems, IDE/editor, debugging, local services and containers | Open |
| Performance | CPU, RAM, storage I/O, build latency, GPU acceleration and battery usage constraints | Open |
| Persistence | Which sources, caches, environments and secrets survive rollback/reinstall? | Open |
| Threat model | Trusted personal code vs external repositories, build scripts, downloaded binaries, security research | Open |
| Recovery | Backup, clean rebuild, rollback, offline availability and acceptable downtime | Open |
| Administration | Update cadence, automation, consistency, software channels | Open |

## Candidate deployment models (not a recommendation yet)

| Model | Why consider it | Material trade-offs to resolve |
| --- | --- | --- |
| **WSL2 within Windows** | Low switching cost for Linux CLI and common userspace toolchains | Different kernel/integration and isolation characteristics; depends on Windows host; not automatically suitable for kernel/hardware work |
| **Linux virtual machine** | Full guest OS, snapshots and reproducible environments while keeping a host desktop | Virtualization overhead and hardware pass-through constraints; sharing untrusted workloads with the host needs a threat assessment |
| **Dedicated native Linux installation** | Direct hardware access and native desktop/kernel environment | Boot/storage integration, updates, backup, recovery and potential impact on existing installations |
| **Remote Linux development host** | Separate execution, potentially independent resources | Network dependency, remote operations cost, latency, hardware access, recovery |
| **Portable/external Linux** | Move a development environment between computers | Device/firmware compatibility and extra boot/storage complexity; not justified by default |

These are **deployment alternatives**. Containers (e.g. OCI/Distrobox/devcontainers)
and language-specific package managers are additional toolchain/isolation choices,
not necessarily alternatives to a host OS.

## Initial architectural hypotheses — unapproved

- Separate the **base OS/platform**, **toolchains/containers** and
  **persistent sources and user configuration** so routine system replacement
  does not accidentally discard work.
- Prefer a clean, reproducible environment over preserving years of unmanaged
  package state. Precisely which artifacts are declared versus backed up is TBD.
- Decide Windows/WinOps integration explicitly: do not assume the security
  workstation should also execute arbitrary development dependencies.
- Select the **least complex model that actually satisfies the workload**, then
  choose the distribution, disk/filesystem, encryption and installer.
- The proven `portable/` AutoYaST/VM harness may offer reuse **only after**
  its assumptions have been checked against LinuxDev's own requirements.

## Concept milestones

1. Establish the development workloads and operating constraints.
2. Write `BUSINESS_REQUIREMENTS.md` with **confirmed** requirements;
   clearly distinguish requirements from examples and technology suggestions.
3. Compare viable deployment models against these requirements and eliminate
   inappropriate options using documented evidence.
4. Write `ARCHITECTURE.md` with a decision log, supported product versions,
   explicit compromises, and an acceptance plan.
5. Only then create provisioning artifacts and, if justified, a focused VM/
   hardware validation harness.

## Confirmed so far

- LinuxDev has a **separate directory and conceptual scope** in the `linux`
  repository.
- No particular distribution, target disk, hardware, execution model,
  security policy, or software stack has yet been selected for LinuxDev.
