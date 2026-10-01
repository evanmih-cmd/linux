# Provisioning economics

## Purpose

This file tracks the provisioning candidates by **total lifecycle cost** while
preserving all authoritative requirements in `BUSINESS_REQUIREMENTS.md`.

Product First determines the order of investigation. Economy First determines
which requirement-satisfying result is preferable. Neither rule bans custom
components.

## Hard gates

A production provisioning path must satisfy all of these together:

- production/GA installation path;
- baseline installation and bare-metal recovery work offline;
- unattended configuration is carried by the installation medium itself;
- destructive work is bound to the intended removable SSD by a persistent,
  unambiguous identity and fails if that identity is absent;
- the host internal disk and ESP are not modified;
- provisioning does not require persistent host NVRAM/BootOrder mutation;
- Secure Boot remains enabled;
- the selected BLS boot path supports the normal measured TPM2+PIN unlock;
- the owner LUKS passphrase remains available for emergency portability;
- the target uses the supported Btrfs/Snapper system layout;
- construction and verification of the installer artifact are repeatable.

A lower-cost candidate that fails a hard gate is not cheaper; it is incomplete.

## Current lowest-delta candidate

The current candidate is:

```text
verified official Tumbleweed Offline Image
+ AutoYaST profile embedded in the installation medium
    exact <drive><device>/dev/disk/by-id/...</device>
    no explicit partition list
    general/storage/proposal supplies encryption_password
    bootloader = systemd-boot
    secure_boot = true
    update_nvram = false
+ tiny installer-only YaST driver update for the missing
  systemd-boot AutoYaST update_nvram import
```

This is a candidate, not yet an architectural selection. It must pass the live
VM gates below.

## Why the storage delta is currently zero

Current `yast-storage-ng` already composes the needed mechanisms:

1. `AutoinstDrivesMap#find_disk` resolves a fixed AutoYaST drive device using
   `devicegraph.find_by_any_name`. Persistent udev links such as
   `/dev/disk/by-id/...` therefore resolve to the actual disk. Its own tests
   verify that a udev link is converted to the corresponding kernel disk name.
2. When the selected drive has no explicit partitions,
   `AutoinstProposal#propose_devicegraph` intentionally falls back to the
   normal guided product proposal.
3. `proposal_settings_for_disks` restricts that guided proposal to
   `drives.disk_names`, so the product proposal receives only the exact disk
   selected by the AutoYaST drive section.
4. `AutoinstSpaceMaker#cleaned_devicegraph` applies destructive cleanup only
   while iterating entries in that drives map. A host disk that is not in the
   map is therefore not a cleanup target.
5. Tumbleweed's current product control file selects:
   `systemd_fde`, `argon2id`, and `tpm2+pin`.
6. `ProposalSettings#load_encryption` imports those product defaults.
   AutoYaST creates those settings from the current product first and permits
   `encryption_password` as a profile override without replacing the method,
   PBKDF, or authentication defaults.
7. The guided devices planner copies the resulting password, encryption method,
   PBKDF and authentication to the planned encrypted device.

Thus the profile can potentially combine exact persistent target identity with
the stock Tumbleweed storage/security proposal instead of reimplementing the
partition layout.

## Remaining bootloader delta

Current `yast-bootloader` has the required runtime capability but an AutoYaST
serialization omission.

`Bootloader::SystemdBoot`:

- has an `update_nvram` property;
- defaults it to `true`;
- writes it to `/etc/sysconfig/bootloader`;
- is installed through `sdbootutil`.

Current `AutoyastConverter#import_systemd_boot` imports `timeout` and
`secure_boot` but does not import `global/update_nvram`.

The minimum runtime correction is conceptually:

```ruby
value = data.global.update_nvram
bootloader.update_nvram = value == "true" unless value.nil?
```

An upstream-quality change should also export the field and add unit tests.
For this workstation, only the import is required by the installation runtime
because the profile is version-controlled and authored directly.

After import, no private bootloader implementation is needed:
`SystemdBoot#prepare` writes the effective sysconfig and stock `sdbootutil`
honors `UPDATE_NVRAM=no` by using its no-variable behavior. The installed
target can therefore use the stock Tumbleweed package.

## Secret-separation gate

Current upstream YaST/sdbootutil integration exposes another cost item that must
be verified against the exact Offline Image packages before acceptance.

For `systemd_fde` with `tpm2+pin`, current YaST bootloader code passes the
storage encryption password to the legacy generic `sdbootutil` keyring secret.
Current sdbootutil treats that generic secret as a backward-compatible fallback
for the TPM2 PIN. Thus the stock automated path can make the LUKS password and
the normal TPM PIN the same value.

That is not the desired operational model: the emergency LUKS credential must
remain suitable against offline attack, while the normal TPM PIN can rely on TPM
rate limiting and should remain practical for routine boot.

The cheapest product-compatible separation candidate is currently:

1. AutoYaST asks for the LUKS/recovery passphrase and supplies it to the normal
   storage proposal.
2. A second password-style AutoYaST question receives the TPM PIN without
   embedding it in the installation medium.
3. The question's supported script hook places that PIN only in the
   `%user:sdbootutil-tpm2-pin` kernel-keyring entry. Current sdbootutil gives
   that specific key precedence over the legacy generic key supplied by YaST.
4. The key is short-lived and exists only in the installer environment; the
   target receives the resulting TPM enrollment, not the clear-text PIN file.

This avoids an FDE fork and uses documented AutoYaST ask/script plus documented
sdbootutil secret-input mechanisms. It is still custom installer glue and must
be live-tested. The exact Snapshot20260930 RPMs are authoritative; upstream
`master` is only research evidence until the ISO package contents are checked.

## Delivery cost of that delta

openSUSE already provides the Driver Update / installation-media tooling:

- `mkdud` can replace files in the installation system or inject an updated
  package;
- `mkdud --install instsys` can limit an RPM update to the installer rather
  than installing it in the target;
- `mkmedia --initrd <dud>` integrates a DUD into an otherwise stock
  installation image;
- `mkmedia` preserves the installation-media model instead of requiring a new
  distribution to be built.

So the candidate custom ownership is currently limited to a tiny installer-time
delta plus reproducible media construction, not an ongoing fork in the
installed workstation.

The maintenance cost of that delta is:

- when adopting a new Offline Image, check whether upstream now imports
  `update_nvram` for systemd-boot;
- if not, verify the tiny overlay still applies to that YaST version;
- rebuild the installer artifact and rerun the provisioning gates;
- if upstream fixes the omission, delete the delta.

## Alternatives and present cost picture

| Candidate | Product coverage | Custom lifecycle cost | Current blocking fact |
|---|---|---|---|
| Agama Live ISO | Native declarative target, TPM/FDE and no-NVRAM controls | Low configuration cost | Public image is development/testing and baseline packages are not offline |
| Offline Image + explicit AutoYaST partition layout | Production/offline; exact by-id target | Higher: profile owns more storage topology and TPM authentication needs additional handling | Duplicates product storage policy and loses the cheapest product-default path |
| Offline Image + exact-drive/no-partitions AutoYaST fallback | Production/offline; exact by-id target; stock product storage/FDE defaults | Currently one tiny installer-only bootloader import delta | Must be proven live |
| Switch distribution/product | Potentially zero openSUSE-specific delta | Migration/research/revalidation cost across boot, FDE, rollback, updates and hardware | No alternative has yet demonstrated a lower total requirement-satisfying cost |

The third row is therefore the current path to validate first under Product
First + Economy First. That is a sequencing decision, not a final selection.

## Required live proof before promotion

The candidate is not accepted until a two-disk VirtualBox run proves:

1. networking is disabled for the entire baseline installation;
2. disk 0 represents the ASUS internal disk and contains partition/filesystem
   sentinel state;
3. disk 1 has the persistent identity named by the AutoYaST profile;
4. the installer fails rather than selecting another disk when that identity is
   absent;
5. with the identity present, only disk 1 is changed;
6. disk 0 GPT/partition/filesystem/sentinel evidence is unchanged after install;
7. effective target storage is the Tumbleweed Btrfs/Snapper layout;
8. effective encryption is LUKS2/systemd_fde with `tpm2+pin` enrollment plus
   the owner passphrase path;
9. effective `/etc/sysconfig/bootloader` contains the no-NVRAM setting;
10. VM EFI variable state shows no provisioning-created persistent boot entry or
    BootOrder mutation;
11. the target ESP contains the removable fallback boot artifact;
12. the installed system cold-boots successfully with Secure Boot enabled.

Only after those observations should the candidate replace the open
provisioning gate in `ARCHITECTURE.md`.
