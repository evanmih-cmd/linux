# LinuxDev — business requirements

## Authority and scope

This document records the product requirements agreed in the 2026-10-17
conversation. Requirements are authoritative; examples and prospective
mechanisms are not. The host is intentionally a **small infrastructure product**
with three user-facing duties, not a new development framework.

## BR-1: Native Linux host

**Requirement:** LinuxDev must be a native Linux installation on the existing
ASUS TUF A14 FA401EA, able to use the platform's hardware without a Windows or
WSL virtualization layer on the critical inference path.

## BR-2: Child-environment execution

**Requirement:** Host Factory and its child projects in their own executable,
persistent Linux environments. The host must provide necessary generic substrate,
resource management and lifecycle; the projects retain their own toolchains,
dependencies and operational semantics.

**Non-requirement:** Install all Factory language/framework/build dependencies
in the LinuxDev root OS.

## BR-3: Existing WSL2 environments continue *as they are*

**Requirement:** Existing Windows WSL2 distributions are first-class environments
on LinuxDev. They must be usable with their existing root filesystems, installed
packages, accounts and required persistent working state, without mandatory
reprovisioning, cloning, package reinstallation, state export/import or migration
to another canonical environment.

This is an **interoperability requirement**, not a claim that Microsoft WSL2
itself runs natively on Linux. Platform-specific host integrations may require
adaptation without altering the canonical working environment.

## BR-4: Bidirectional durable state

**Requirement:** Changes made while operating the same working environment
under LinuxDev persist and are available when it is next operated under Windows
WSL2, and Windows-made changes are available on the next LinuxDev run.

**Safety invariant:** The same mutable guest filesystem must never be writable
by both hosts simultaneously. Switching OS must have a safe close/flush/attach
lifecycle. Recovery must not silently roll back working state.

## BR-5: Ephemerd on Linux

**Requirement:** Factory's ephemerd-based CI job execution must run on LinuxDev,
respecting the relevant Factory runner image, dispatch policy and job contracts.

**Security condition:** Container isolation is not automatically equivalent to
Hyper-V VM isolation. Any change in accepted trust boundaries must be explicit.

## BR-6: Operator desktop

**Requirement:** Provide a comfortable and fully functional graphical Linux
desktop for interactive operation and administration. It must not require using
a development container as the operator's graphical workstation.

## BR-7: Native high-memory LLM inference

**Requirement:** Run compute- and GPU-memory-intensive local LLMs with the
minimum useful overhead and direct access to AMD Radeon 8060S / unified RAM,
aiming to exceed the practical **48 GB Windows graphics-memory limit**.

**Acceptance direction:** Evaluate useful model memory including weights,
KV cache and headroom for the OS, desktop and simultaneously running children.
A larger reported GTT/VRAM number alone is not sufficient evidence.

## BR-8: Windows continuity

**Requirement:** Existing Windows installations and WSL2 environments remain
usable. LinuxDev must not permanently damage their boot, disk, encryption
or recovery paths, and no destructive installation action may guess its target.

## BR-9: Practical lifecycle

**Requirement:** Recovery, host updates, child-environment launch and switching
between Windows and LinuxDev must be operationally simple and avoid routine
manual state reconstruction.

## BR-10: Total-cost discipline

**Requirement:** Prefer existing supported virtualization/container/OS/GPU
capabilities, with narrow glue only where compatibility demands it. Optimize
human time and whole-life cost, not the number of rules or custom subsystems.

## Acceptance gates (product-level)

A. An existing WSL2 environment is run under LinuxDev without re-creating
   its OS/packages/accounts; meaningful mutations survive LinuxDev shutdown
   and are present on the next Windows WSL2 launch; the reverse direction
   is proven too. Include the separately persisted artifacts actually used
   by the current Factory environment.
B. Ephemerd executes a representative Factory Linux CI job on LinuxDev with
   the intended image and network/security policy, not only `--version`
   or daemon startup.
C. Actual LLM inference on the ASUS exceeds the Windows 48 GB *usable-memory
   constraint* for a materially larger workload while retaining system
   stability and useful token throughput.
D. A complete graphical session works, and either OS can still be booted
   and used normally with its own persistent state intact.
