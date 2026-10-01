# Portable workstation — VirtualBox proof plan

## Purpose

This plan proves the parts of the portable-workstation architecture that Oracle
VirtualBox can exercise. It is not a substitute for the ASUS FA401EA hardware
validation gates.

The VM is a disposable proof environment. The production provisioning medium
remains subject to the GA-only rule in `ARCHITECTURE.md`.

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
- the unattended profile is embedded as `/autoinst.json` in the Agama
  installation image; the installer must discover it by the supported media
  mechanism and start without an external control-plane injecting configuration;
- networking only as needed for installation/update testing;
- virtual TPM only when the installed VirtualBox release exposes a usable TPM
  mode;
- no dependency on Windows filesystem mounts or WSL/Windows interop.

The WSL control plane may access only the explicitly allowed Windows endpoints
already documented in issue #1.

## Gates

| # | Claim | Type | Evidence |
|---|---|---|---|
| 1 | Agama installs Tumbleweed unattended from the profile embedded in the installation medium | BEHAVIOR | Boot the generated Agama image containing `/autoinst.json`; installation must start from media discovery without API/UI configuration injection, complete, and boot the installed system |
| 2 | Installer touches only the portable target while an ASUS-internal disk is present | BOTH | Before install, record the internal disk partition/filesystem/sentinel state and the portable disk identity; after install, prove the portable disk changed as intended and the internal disk state is unchanged |
| 3 | UEFI installation uses the Tumbleweed systemd-boot/BLS path | BOTH | Read effective bootloader/BLS state, then reboot and boot successfully through it |
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

1. Establish the narrow VirtualBox control plane from WSL.
2. Inventory the installed VirtualBox release and available firmware/TPM
   capabilities.
3. Create the disposable UEFI VM with two disks: internal-ASUS guard disk first,
   portable target disk second.
4. Build the VM harness from the verified Agama ISO by adding the declarative
   profile as `/autoinst.json` using Agama's supported installation-medium
   mechanism. This generated image is also the image intended to be written to
   the physical installer USB later.
5. Boot that image and let Agama discover the embedded profile and run the
   installation unattended; do not drive installation by injecting runtime
   configuration through the Agama API/UI.
6. Execute CONFIG gates from the installed system.
7. Execute BEHAVIOR gates by rebooting, updating, failing and rolling back the
   live VM.
8. Record each observation in issue #1 and promote only mechanisms that remain
   compatible with the production/GA architecture.
