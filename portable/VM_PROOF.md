# Portable workstation — VirtualBox proof plan

Execution harness, observability channels, timeouts and stop rules are defined
in `VM_TEST_PLAN.md`. This file defines what must be proven; `VM_TEST_PLAN.md`
defines how each live gate is executed.

## Purpose

This plan proves the parts of the portable-workstation architecture that Oracle
VirtualBox can exercise. It is not a substitute for the ASUS FA401EA hardware
validation gates.

The proof uses one persistent registered VM. It is reconfigured between gates
but is not cloned or multiplied. The production provisioning medium remains
subject to the GA-only rule in `ARCHITECTURE.md`.

## Evidence rule

Every gate is classified before execution.

- **CONFIG**: read the effective configuration/state and prove the required
  value is present.
- **BEHAVIOR**: exercise the live system and prove the observed outcome.
- **BOTH**: prove configuration and behavior independently.

No gate passes because a test fixture contains the expected value. A declaration
is evidence only for a CONFIG claim; runtime claims require live execution.

## VM boundary

The proof VM must have:

- UEFI firmware;
- two virtual disks: disk 0 represents the ASUS internal system disk and disk 1
  represents the removable workstation target;
- the internal-system disk is deliberately present during installation and is
  pre-populated with sentinel partition/filesystem data whose pre/post state is
  compared;
- the verified official Offline ISO is attached as the immutable base medium;
- the Desktop-Linux provisioning layer is attached as a separate small local
  medium in the VM, modelling the custom area that will coexist on the same
  writable physical USB device;
- the installer must discover the unattended profile and installer delta from
  those local media without a network or external control plane;
- networking is disabled during provisioning proof and enabled only for later
  update/workload tests;
- virtual TPM only when the installed VirtualBox release exposes a usable TPM
  mode;
- no dependency on Windows filesystem mounts or WSL/Windows interop.

The WSL control plane may access only the explicitly allowed Windows endpoints
already documented in issue #1.

## Gates

| # | Claim | Type | Evidence |
|---|---|---|---|
| 1 | The selected production installer installs Tumbleweed unattended from the verified official Offline ISO plus the Desktop-Linux layer with networking disabled | BEHAVIOR | Boot the official ISO with the local layer attached, prove no guest network is available, let the installer discover its profile/delta from local media, complete installation, and boot the installed system |
| 2 | Installer touches only the portable target while an ASUS-internal disk is present | BOTH | Before install, record the internal disk partition/filesystem/sentinel state and the portable disk identity; after install, prove the portable disk changed as intended and the internal disk state is unchanged |
| 3 | UEFI installation uses the final selected supported BLS/boot path | BOTH | Read effective bootloader/BLS state, then reboot and boot successfully through it |
| 4 | NVRAM-update policy is disabled for portable provisioning | CONFIG | Read effective installer/bootloader state showing the supported no-NVRAM-update setting |
| 5 | External-style fallback boot artifact exists | CONFIG | Inspect ESP for the removable fallback path required by the architecture |
| 6 | Root storage is LUKS2 over Btrfs with supported Snapper layout | CONFIG | Read block, crypt, filesystem, subvolume and Snapper state from the installed system |
| 7 | Owner passphrase unlock works | BEHAVIOR | Cold boot with TPM path unavailable/unused and unlock with the owner passphrase |
| 8 | TPM-backed primary unlock works when VirtualBox TPM can model the required path | BOTH | Read enrollment state; cold boot and observe successful TPM-backed unlock |
| 9 | Unexpected measured-state change prevents normal TPM unlock when the VM can model it | BEHAVIOR | Change a measured pre-unlock component and prove normal TPM unlock fails |
| 10 | User/application state is outside root rollback | BOTH | Inspect mount/subvolume layout; write user-state marker, roll back root, prove marker survives |
| 11 | Snapper rollback restores a known-good root | BEHAVIOR | Introduce a root-state change, create/choose rollback point, rollback and verify old root state is restored |
| 12 | `transactional-update dup` creates/activates a new snapshot | BOTH | Inspect transaction/snapshot state; perform update and boot/activate the new state |
| 13 | Failed transactional update does not become the active root | BEHAVIOR | Force a real transaction failure and prove the failed state is not activated |
| 14 | Userspace-only update can activate through systemd soft reboot | BOTH | Verify supported restart policy; perform a qualifying update and observe soft reboot into the new root |
| 15 | Kernel-level update requires full reboot | BEHAVIOR | Apply a kernel transition and prove a firmware-level reboot is required/used before release |
| 16 | kexec is disabled | BOTH | Read effective kexec/restart configuration; attempt the relevant path and prove it is not selected/available |
| 17 | Sensitive workload is blocked before maintenance success | BEHAVIOR | Boot into an update-required or forced-failure state and prove the workload target cannot start |
| 18 | Recovery/admin path remains available after maintenance failure | BEHAVIOR | Force maintenance failure and prove administrative recovery remains reachable |
| 19 | Successful/current maintenance releases the sensitive workload | BEHAVIOR | Complete the maintenance path and prove the workload target becomes startable |
| 20 | Maintenance result is explicit | BEHAVIOR | Exercise current/success/failure paths and observe distinct user-visible result states |

## Current live provisioning evidence

The separate-media provisioning path has now passed these live subgates:

- **OEMDRV discovery: PASS.** With networking disabled, the unchanged official
  Snapshot20260930 ISO discovered the separate OEMDRV layer and AutoYaST
  displayed the source-controlled recovery, TPM2 PIN and administrator asks.
- **Absent exact target: PASS.** With only the ASUS-like guard VDI attached,
  storage proposal stopped at `Create partition plans` with:
  `Disk '/dev/disk/by-id/ata-PORTABLE_WORKSTATION_SSD_PORTABLETARGET000001'
  was not found`.
- **Internal-disk negative safety: PASS.** The guard VDI SHA-256 was
  `de1c73ea1d0c94d5c30caa571c8e4150ebfb2151fb879862f6619c5895b42fe9`
  immediately before and after the failed proposal.

This does not yet complete gate 1 or gate 2: the positive target-present
installation still has to complete and the internal guard must remain unchanged
through that successful install.

Screenshot evidence is stored under `provisioning/evidence/`; detailed hashes
and layer identity are recorded in `provisioning/LAYER_PROOF.md`.

## Non-VM claims

VirtualBox does not approve these claims:

- ASUS one-time boot selection behavior across a full reboot;
- absence of unwanted physical-host NVRAM/internal-ESP mutation during real
  removable-media provisioning;
- real Secure Boot key/firmware behavior on the ASUS;
- real TPM2+PIN UX and measured-state behavior when VirtualBox cannot model it;
- the actual owner-controlled USB/HID authorization device;
- emergency portability on another physical compatible host.

Those remain physical validation gates.

## Execution order

1. Resolve the production provisioning gate in `ARCHITECTURE.md`; no VM
   installer result is promoted while the installer itself still violates a
   requirement.
2. Establish the narrow VirtualBox control plane from WSL.
3. Inventory the installed VirtualBox release and available firmware/TPM
   capabilities.
4. Create the disposable UEFI VM with two disks: internal-ASUS guard disk first,
   portable target disk second.
5. Build the small Desktop-Linux provisioning layer and verify its manifest;
   attach it alongside the unchanged verified official Offline ISO.
6. Disable guest networking and perform the unattended installation.
7. Execute CONFIG gates from the installed system.
8. Execute BEHAVIOR gates by rebooting, updating, failing and rolling back the
   live VM.
9. Record each observation in issue #1 and promote only mechanisms that remain
   compatible with the production/GA architecture.