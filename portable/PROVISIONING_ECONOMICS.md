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

The current candidate is deliberately split into two independently verifiable
logical layers:

```text
immutable base:
  verified official Tumbleweed Snapshot20260930 Offline ISO
  SHA-256 0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99

small Desktop-Linux layer:
  AutoYaST profile
    exact /dev/disk/by-id target
    initialize = true
    no explicit partition list
    recovery/LUKS passphrase ask
    separate TPM2 PIN ask
    systemd-boot + secure_boot=true + update_nvram=false
  same-DVD stock keyctl/libkeyutils for the installer runtime
  minimal installer-only systemd-boot AutoYaST import correction
  minimal installer-only NetworkManager offline target-write correction
  complete manifest + hashes
```

In VirtualBox these are two attached media. On the final writable USB device
they are co-located after the verified upstream ISO is written to the device.

The large upstream ISO is no longer rebuilt for routine profile/overlay
iterations. A monolithic derived ISO is only an optional diagnostic/archive
artifact.

This is still a candidate until the live VM gates pass.

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

The Snapshot20260930 YaST/sdbootutil integration exposes another cost item.
Its exact Offline Image packages have now been inspected; the remaining gate is
live enrollment behavior in the proof VM.

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
4. The key exists only in the installer kernel keyring and is never written to
   the profile or target filesystem; reboot destroys the installer keyring.
   The target receives the resulting TPM enrollment, not a clear-text PIN file.

This avoids an FDE fork and uses the stock AutoYaST ask/script hook plus the
stock sdbootutil secret-input mechanism. It is still custom installer glue and
must be live-tested. All statements above have been checked against the exact
Snapshot20260930 RPMs rather than upstream `master`.

## Delivery cost of that delta

The lowest-cost delivery model is now the two-layer model rather than routine
whole-ISO reconstruction.

The immutable Offline ISO is verified once and reused unchanged. Development
iterations rebuild only the small Desktop-Linux layer. That layer must contain
an exhaustive manifest so its complete custom content can be verified
independently.

For the VM proof:

```text
official Offline ISO
+ small local Desktop-Linux layer medium
```

For production USB deployment:

```text
verify official ISO
→ write it to USB with Rufus or equivalent
→ add the verified Desktop-Linux layer to the same writable USB
```

The installer-side transport for the custom files must use supported
local-media mechanisms and must pass live proof. Network delivery or a host-side
control plane is not an acceptable substitute.

This lowers lifecycle cost relative to repeated `mkmedia` reconstruction:

- edits to `autoinst.xml` do not require reading/writing/hashing 4.4 GiB;
- upstream ISO provenance remains directly recognizable;
- the custom trust surface is a small manifestable object;
- VM iteration and final physical deployment use the same logical inputs;
- adopting a new Snapshot means revalidating the layer against the new
  installer, not treating a large locally re-signed ISO as the primary source.

The previous monolithic derived ISO remains useful historical/static evidence,
but it is no longer the normal delivery or development loop.

The maintenance cost of the custom delta is:

- verify the signed metadata and ISO hash when adopting a new Offline Image;
- check whether upstream now imports `update_nvram` for systemd-boot;
- check whether the installer runtime now supplies the keyring tooling needed by
  the supported sdbootutil PIN input;
- check whether NetworkManager target-only writes still call
  `ensure_network_running` when `apply_config=false`;
- delete any layer component made unnecessary by upstream;
- rebuild and reverify only the small custom layer;
- rerun the provisioning gates.

## Alternatives and present cost picture

| Candidate | Product coverage | Custom lifecycle cost | Current blocking fact |
|---|---|---|---|
| Agama Live ISO | Native declarative target, TPM/FDE and no-NVRAM controls | Low configuration cost | Public image is development/testing and baseline packages are not offline |
| Offline Image + explicit AutoYaST partition layout | Production/offline; exact by-id target | Higher: profile owns more storage topology and TPM authentication needs additional handling | Duplicates product storage policy and loses the cheapest product-default path |
| Offline Image + separate Desktop-Linux AutoYaST layer | Production/offline; upstream ISO remains independently verified; exact by-id target; stock storage/FDE defaults | Small manifestable profile/installer delta; no routine 4.4 GiB rebuild | Local-media discovery/update transport and full installation behavior must be proven live |
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