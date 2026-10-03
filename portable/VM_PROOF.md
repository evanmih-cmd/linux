# Portable workstation — VirtualBox proof plan

## Purpose

This plan validates the final selected **openSUSE Tumbleweed** topology where
VirtualBox can model it. It does not approve ASUS firmware behavior or the real
Ledger device.

No VM experiment should be run from this document until the current
documentation/source gates in `ARCHITECTURE.md` are ready for behavioral proof.

## Evidence rule

- **CONFIG** — inspect effective configuration/state.
- **BEHAVIOR** — exercise the live system and observe the outcome.
- **BOTH** — prove both independently.

A fixture containing an expected value is not evidence that the guest actually
uses it.

## VM boundary

The disposable proof VM has:

- UEFI firmware;
- disk 0 representing the ASUS internal disk, pre-populated with sentinel state;
- disk 1 representing the removable workstation target;
- networking disabled for baseline provisioning;
- virtual TPM only when the installed VirtualBox version can model the required
  flow;
- Secure Boot when the VM firmware permits the selected chain;
- no dependence on host filesystem mounts or WSL interop from inside the guest.

## Final topology under test

```text
external-style ESP
└── stock openSUSE removable boot path / vendor-signed UKI candidate

outer LUKS2
└── LVM
    ├── root LV  → Btrfs/Snapper
    ├── home LV  → persistent marker/browser-state surrogate
    └── swap LV  → encrypted disk-backed swap
```

Credentials are deliberately separate:

- short TPM2 PIN for the normal TPM-bound path;
- strong LUKS recovery passphrase for offline/new-host recovery.

## Gates

| # | Claim | Type | Evidence |
|---|---|---|---|
| 1 | Official Tumbleweed Offline Image + embedded AutoYaST profile installs with networking disabled | BEHAVIOR | Boot final media with guest network absent and complete baseline install |
| 2 | Destructive work is bound to the exact portable disk identity | BOTH | Profile names stable disk identity; absent identity fails; present identity changes disk 1 only |
| 3 | Internal-disk sentinel state is unchanged | BOTH | Compare disk 0 GPT/partitions/filesystems/sentinel before and after |
| 4 | Provisioning leaves persistent UEFI variables/BootOrder unchanged | BOTH | Compare EFI variable state before and after install |
| 5 | External ESP contains the standard removable fallback path | CONFIG | Inspect ESP artifacts |
| 6 | Final storage is one outer LUKS2 containing LVM root/home/swap LVs | CONFIG | Inspect block/crypt/LVM/filesystem state |
| 7 | Root is Btrfs/Snapper and home is a separate preserved filesystem | CONFIG | Inspect mounts/subvolumes/snapshot config |
| 8 | Swap is real disk-backed swap inside the encrypted boundary and requires no second unlock | BOTH | Inspect swap device; cold boot observes only intended normal credential path |
| 9 | Strong recovery passphrase independently unlocks the outer LUKS2 volume | BEHAVIOR | Disable/unavailable TPM path and unlock with recovery passphrase |
| 10 | Normal TPM2 path uses a distinct short PIN, not the recovery passphrase | BOTH | Inspect enrollment/installer secret path and cold-boot with TPM PIN |
| 11 | TPM PIN is not persisted in installation media or a clear-text target file | CONFIG | Inspect generated media/profile/target secret locations |
| 12 | Secure Boot succeeds through the selected stock openSUSE chain | BOTH | Inspect Secure Boot state and boot successfully |
| 13 | Official vendor-signed UKI is the authenticated pre-unlock execution path | BOTH | Inspect loaded image/boot state and observe prompt path |
| 14 | Unauthorized pre-unlock modification cannot produce a trusted counterfeit PIN prompt | BEHAVIOR | Modify a relevant ESP/BLS/early-boot artifact and prove trusted normal unlock does not proceed |
| 15 | Normal UKI/kernel update needs no owner signing or recurring MOK enrollment | BOTH | Apply update, inspect artifacts/trust state and reboot |
| 16 | Snapper rollback restores known-good root without rolling home back | BOTH | Write independent root/home markers, rollback root, prove only root marker changes |
| 17 | Previous root remains bootable through the selected authenticated boot path | BEHAVIOR | Boot/select old snapshot and verify usable known-good system |
| 18 | Managed-update failure leaves a usable previous-system recovery point | BEHAVIOR | Force a real update failure and prove previous root remains recoverable |
| 19 | Sensitive workload gate blocks work until maintenance policy succeeds | BEHAVIOR | Exercise current/success/failure states |
| 20 | Maintenance result is explicit and stale executable state is cleared before release | BOTH | Observe result state and process/restart behavior |
| 21 | Reinstall replaces root while preserving the persistent home LV byte-for-byte/logically intact | BOTH | Place persistent markers, execute reinstall profile, compare home state and root identity |
| 22 | Reinstall can establish fresh TPM enrollment after root replacement | BOTH | Complete reinstall and cold boot through normal TPM path |

## Physical-only gates

VirtualBox cannot approve:

- exact ASUS TUF A14 FA401EA firmware/Secure Boot/TPM behavior;
- hardware root-of-trust/firmware measurement behavior;
- whether one-time external selection survives a firmware reboot;
- real external-SSD enumeration quirks;
- real Ledger Chrome/WebHID behavior;
- portability/recovery on a second compatible physical host.

Those remain physical acceptance tests after the VM proof.

## Execution order

1. Finish source/doc proof of the selected UKI/MOK/sdbootutil lifecycle.
2. Build the final Offline Image + AutoYaST artifact.
3. Create the two-disk disposable VM.
4. Run offline exact-target provisioning.
5. Run CONFIG gates.
6. Run boot/FDE/Secure-Boot behavioral gates.
7. Run update/rollback/workload-gate tests.
8. Run destructive reinstall-preserve-home proof.
9. Record every observation in issue #1.
10. Move to ASUS hardware only after VM-capable gates pass.
