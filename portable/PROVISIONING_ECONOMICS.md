# Provisioning economics

## Purpose

This file tracks the smallest provisioning delta for the **selected**
openSUSE Tumbleweed product while preserving
[`BUSINESS_REQUIREMENTS.md`](BUSINESS_REQUIREMENTS.md).

Product selection is no longer open merely because provisioning still has proof
work. Reopen selection only if the remaining delta becomes security-sensitive
owner infrastructure rather than narrow installer plumbing.

## Hard gates

Production provisioning must simultaneously provide:

- production/GA Tumbleweed Offline Image;
- offline baseline install and bare-metal recovery;
- unattended profile carried by the media;
- fail-closed stable identification of the removable target;
- no write to the host internal disk/ESP;
- no persistent host NVRAM/BootOrder mutation;
- Secure Boot;
- authenticated normal pre-unlock path;
- one outer LUKS2 boundary;
- **separate** short TPM2 PIN and strong owner recovery passphrase;
- LVM root/home/swap separation inside LUKS2;
- root Btrfs/Snapper;
- preserve-home system reinstall;
- reproducible media construction/provenance.

A cheaper path that misses one hard gate is incomplete, not economical.

## Selected provisioning direction

```text
verified official Tumbleweed Offline Image
+ AutoYaST profile embedded in installation media
    exact /dev/disk/by-id/... target
    final LUKS2 → LVM topology
    strong recovery passphrase entered by owner
    short TPM PIN entered separately
    Btrfs root + persistent home LV + swap LV
    stock Secure Boot/BLS/sdbootutil mechanisms
+ only the minimum installer-time adapters still required by the exact ISO
```

The installed workstation must remain stock where security-sensitive lifecycle
matters. Installer adaptations may feed existing product properties/secrets but
must not become a custom bootloader, FDE engine, TPM policy implementation or
private signing service.

## Exact-target economics

AutoYaST/yast-storage-ng can resolve a fixed drive identity through persistent
udev names and constrain destructive storage planning to the named drive.

The final profile must explicitly prove the selected external SSD identity and
fail if it is absent. The internal ASUS disk is present during proof as a guard
disk with sentinel state.

## Storage topology economics

Earlier work tried to minimize layers. The final architecture deliberately adds
LVM because requirements 13 and 15 create a real lifecycle boundary requirement.

```text
LUKS2
└── LVM
    ├── root LV  → disposable/replaceable Btrfs system
    ├── home LV  → persistent state preserved by reinstall
    └── swap LV  → encrypted disk-backed swap
```

This is cheaper than relying on filesystem-subvolume conventions during a
destructive reinstall because the installer can preserve or destroy whole LVs
unambiguously.

## Bootloader/no-NVRAM delta

Current YaST/systemd-boot runtime has a no-NVRAM property and current
`sdbootutil` has no-variable/portable behavior. Historical research found an
AutoYaST import omission for the relevant BLS path in the then-current packages.

Before carrying any patch forward, inspect the exact selected Offline Image.

If the omission still exists, the acceptable delta is a tiny installer-only
YaST driver update that imports the already-supported `update_nvram` property.
It must not modify the installed bootloader implementation. If upstream fixed
the omission, delete the delta.

## Secret-separation gate

The normal TPM PIN and the recovery LUKS passphrase must **not** be the same
secret.

Reason:

- the TPM PIN is routine human input and may be short because its security model
  includes TPM authorization/rate limiting;
- the recovery passphrase must withstand offline guessing by an attacker who
  possesses the SSD;
- using the same short value for both would collapse the recovery credential to
  the weaker threat model.

Current `sdbootutil` explicitly exposes separate secret sources:

- current LUKS password: `cryptenroll`;
- recovery key/PIN channels;
- TPM2 PIN: `%user:sdbootutil-tpm2-pin`.

Current/earlier YaST integration may still feed the storage encryption password
into the legacy generic secret, allowing it to become the TPM PIN by fallback.
That behavior is not accepted for this workstation.

The lowest-cost product-compatible separation is:

1. AutoYaST asks for the strong LUKS recovery passphrase and uses it for storage
   creation/recovery.
2. A second password-style AutoYaST question asks for the short routine TPM PIN.
3. A supported installer script hook places that PIN only in
   `%user:sdbootutil-tpm2-pin`.
4. `sdbootutil` consumes the short-lived keyring secret during enrollment.
5. No clear-text PIN is embedded in the media or persisted in the target.

This is custom installer glue, but it composes documented product secret-input
mechanisms and does not own cryptography or TPM policy. It remains acceptable
only while it stays this narrow.

## MOK economics

The selected authenticated-UKI candidate currently requires one-time enrollment
of an openSUSE vendor **public signing certificate** through MOK.

Accepted:

- one-time enrollment on a primary host;
- vendor/project owns the private signing key and UKI signing lifecycle.

Rejected as too costly unless all product paths fail:

- owner-generated Secure Boot key infrastructure;
- owner signing of every kernel/UKI;
- recurring re-enrollment after routine updates.

The proof must establish the actual certificate scope and that ordinary updates
do not turn this one-time cost into recurring administration.

## Reinstall economics

A broken system or broken TPM relationship does not need heroic in-place repair.

The supported recovery objective is:

```text
trusted offline media
→ strong owner recovery passphrase
→ preserve home LV
→ replace root/system
→ recreate stock boot artifacts
→ establish fresh host-specific TPM/MOK state
```

This is cheaper and easier to audit than maintaining repair tooling for every
possible damaged installation state.

The exact AutoYaST preservation semantics must be verified against the selected
packages. Reinstall must fail safely rather than guess which LV is persistent.

## Remaining accepted custom ownership

At the product-selection checkpoint, project-owned provisioning code is limited
to two possible installer-only adapters, each conditional on the exact ISO:

1. import the existing no-NVRAM property if AutoYaST still omits it;
2. deliver a separately entered TPM PIN through the dedicated
   `sdbootutil-tpm2-pin` keyring channel.

Everything else should be declarative product configuration.

## Go/no-go proof

The provisioning path is accepted only when a two-disk VM proof demonstrates:

1. install succeeds fully offline;
2. missing exact target causes failure;
3. internal guard disk remains unchanged;
4. NVRAM remains unchanged;
5. removable fallback boot artifacts exist;
6. final LUKS2→LVM root/home/swap topology exists;
7. recovery passphrase and TPM PIN are distinct and each works only in its
   intended path;
8. TPM PIN is not persisted in media/target clear text;
9. Secure Boot + selected authenticated UKI path boots successfully;
10. reinstall replaces root and preserves home;
11. normal update lifecycle needs no owner signing or recurring MOK work.

If satisfying these gates expands project ownership into boot verification,
private PKI, custom FDE/TPM policy or a bespoke updater, stop and reopen product
selection.
