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
   
**Ephemerd** must also run on LinuxDev with Factory's relevant CI contract intact.
It is an execution service supporting role 1, not an independent fourth
product role. **Leading isolation proposal:** use **one shared Factory execution KVM guest**
for any existing WSL2 root that requires VM semantics **and** for ephemerd.
The WSL `ext4.vhdx` is a filesystem image, not itself a mandate for a VM.
Never create a second ephemerd VM by default; LinuxDev's physical OS and
GPU stay independent.

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
- Ephemerd must be supported on Linux and **isolated from the host OS**;
  authorized Factory administration must directly repair/update its own guest
  domain without a bespoke privileged host updater.
- Local LLM inference uses the physical GPU and shared memory as directly and
  efficiently as practical.
- Product First / Economy First: favor supported products, minimize lifetime
  engineering and operational burden, introduce glue only for a proven gap.

## Still open (do not silently decide)

- Which native Linux distribution/kernel/desktop combination best supports
  gfx1151/Radeon 8060S inference *on this exact ASUS* and a pleasant desktop?
- Exact **zero-copy, bidirectional WSL2 image ownership** and its storage
  placement/unlock across OSes, including crash consistency.
- How WSL-specific host integrations and existing Factory runner services map
  to Linux containers or another compatible runtime.
- Qualify **one shared** Factory guest for existing WSL root and ephemerd,
  or a no-VM WSL namespace mode only where it preserves required isolation;
  guest-root access to WSL data is an explicit trust-boundary consideration.
  Measure real cost against 64 GB of shared GPU/CPU memory.
- Native inference backend and realistic maximum model weights+KV-cache size
  without exhausting memory needed by host/child workloads.
- Host installation and rollback strategy that leaves Windows recoverable.

No partitioning, OS reinstall, package baseline, new VMs or guest migrations
are authorized by this concept draft.
