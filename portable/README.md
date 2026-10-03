# Portable workstation

This directory contains the design and implementation artifacts for a
self-contained security workstation carried on removable storage.

The authoritative product requirements are in
[`BUSINESS_REQUIREMENTS.md`](BUSINESS_REQUIREMENTS.md). The product-selection
research is closed on **openSUSE Tumbleweed** unless a residual implementation
gate proves that a business requirement cannot be met without owner-maintained
security-sensitive infrastructure.

## Documents

- [Business requirements](BUSINESS_REQUIREMENTS.md) — authoritative outcomes.
- [Architecture](ARCHITECTURE.md) — selected Tumbleweed architecture and the
  remaining go/no-go proof gates.
- [Provisioning economics](PROVISIONING_ECONOMICS.md) — smallest supported
  installer delta and its lifecycle cost.
- [VirtualBox proof plan](VM_PROOF.md) — later CONFIG/BEHAVIOR validation of the
  final topology.
- [GitHub issue #1](https://github.com/evanmih-cmd/linux/issues/1) — research
  history, rejected alternatives, corrections, checkpoints and proof evidence.

## Selected direction

```text
openSUSE Tumbleweed
→ official Offline Image + AutoYaST
→ exact removable-SSD target; internal host disk outside authority
→ Secure Boot
→ stock removable EFI path; no persistent UEFI NVRAM writes
→ official vendor-signed UKI path, with the openSUSE signing certificate
  enrolled through MOK on the primary host
→ one outer LUKS2 boundary
   ├── short routine TPM2 PIN for normal boot
   └── separate strong owner recovery passphrase for offline/new-host recovery
→ LVM inside LUKS2
   ├── replaceable Btrfs root + Snapper
   ├── persistent /home volume preserved across system replacement
   └── real disk-backed swap volume; hibernation disabled
→ native openSUSE update/rollback mechanisms
→ sensitive Chrome workload released only after maintenance policy succeeds
→ Ledger through the supported Chrome/WebHID/udev path
```

Btrfs, LVM, MOK and a particular updater are implementation choices rather than
business requirements. They are selected only where they lower total lifecycle
cost while satisfying the required outcomes.

## Credential model

The normal and recovery credentials are deliberately **different**.

- The normal TPM2 PIN is short enough for routine boot and relies on TPM-backed
  authorization/rate limiting.
- The recovery passphrase is high-entropy / high-work-factor material suitable
  for an attacker who has the SSD and can attempt offline guessing.
- The recovery passphrase must work without the original host TPM.
- The TPM PIN is not accepted as the offline recovery secret.

Current `sdbootutil` exposes a dedicated TPM2-PIN secret channel. If YaST on
the selected Offline Image still feeds the storage password into the legacy
generic secret channel, AutoYaST may use a tiny installer-only ask/script hook
to place the separately entered PIN into the supported
`%user:sdbootutil-tpm2-pin` keyring entry. That is residual provisioning glue,
not a new FDE implementation.

## Repository principles

This project follows Factory's Product First + Economy First discipline:

- exhaust supported production product capabilities before custom mechanisms;
- compare total lifecycle cost, including expected security loss for
  irreversible high-value actions;
- for this workstation, silent pre-unlock secret theft is much more expensive
  than fail-closed recovery inconvenience;
- custom code is residual glue only after a product gap is demonstrated;
- RC/preview/test-only product paths are unavailable for production;
- an upstream “experimental” interface label is not by itself a security
  verdict: assess the concrete failure mode, distro ownership and recurring
  lifecycle cost;
- installer/tool limitations do not redefine the business requirements.

## Current phase

Do not restart general OS-selection research unless a residual gate falsifies the
selected product.

The next work is to prove the final Tumbleweed topology:

1. authenticated pre-unlock UKI path and counterfeit-prompt resistance;
2. vendor-managed UKI update/PCR lifecycle without owner signing;
3. Snapper/rollback compatibility with that boot path;
4. AutoYaST reinstall that replaces root while preserving the persistent
   volume;
5. exact-target, offline, no-internal-disk and no-NVRAM behavior on the final
   topology;
6. ASUS TUF A14 FA401EA Secure Boot/TPM behavior plus Chrome + Ledger.
