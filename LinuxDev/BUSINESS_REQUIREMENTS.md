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

## BR-5A: Ephemerd must not administer the LinuxDev host

**Requirement:** A compromised or intentionally guest-root-controlling Factory
execution stack must not acquire root, host filesystem, host storage/RAID, GPU,
host credentials, operator desktop or virtualization-admin authority on
LinuxDev merely because it can manage the runner substrate.

**Requirement:** Authorized Factory administration can directly install,
configure, update, repair, replace and restart ephemerd, its Linux guest OS,
OCI images, credentials and job machinery **inside a bounded Factory-owned
execution domain**, including exceptional recovery actions outside a normal
CI cycle. This must not require a custom trusted host updater/synchronizer.

**Critical distinction:** Authorized Factory control-plane administration
is NOT the same trust category as untrusted candidate code in ordinary CI
jobs. Candidate jobs do not receive the VM admin key, guest root rights,
host virtualizer control or access to Ephemerd's GitHub App private key.

**Practicality:** Reuse an existing, justified Factory/WSL full-kernel guest as
Ephemerd's isolation boundary; never automatically allocate a separate VM
just for Ephemerd. A VHDX filesystem can instead run under a namespace
container where no extra guest kernel is needed, but this does not grant
Ephemerd unrestricted host root authority. Prefer one stock virtualization
boundary, minimizing RAM/CPU/storage overhead against 64 GB UMA inference.
Guest-root authority necessarily reaches WSL data presented to the same
guest: never expose personal or independently protected WSL roots by default.
Retain manual host-owned guest rollback when its entire OS fails; this is
a last-resort recovery, not a permanent privileged host update service.

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
B. Ephemerd executes a representative Factory Linux CI job inside its bounded
   execution domain with the intended image and network/security policy,
   not only `--version` or daemon startup. Factory can also self-update or
   repair ephemerd independently of the daemon's health without privileged
   administration of the physical LinuxDev OS. An ordinary untrusted CI
   job has no access to this administration route.
C. Actual LLM inference on the ASUS exceeds the Windows 48 GB *usable-memory
   constraint* for a materially larger workload while retaining system
   stability and useful token throughput.
D. A complete graphical session works, and either OS can still be booted
   and used normally with its own persistent state intact.
