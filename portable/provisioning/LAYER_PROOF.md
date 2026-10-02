# Snapshot20260930 Desktop-Linux layer proof

## Scope

This records the small provisioning layer used alongside the unchanged,
cryptographically verified openSUSE Tumbleweed Snapshot20260930 Offline ISO.

The layer is the current development and release packaging candidate. The
historical whole-ISO composition proof remains in `PROOF.md`.

## Immutable base identity

Base ISO:

`openSUSE-Tumbleweed-DVD-x86_64-Snapshot20260930-Media.iso`

SHA-256:

`0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99`

The layer records this base identity but does not contain or modify the base
ISO.
## Supported layer mechanism

The layer uses SUSE's YaST Driver Update Disk mechanism rather than a custom
installer loader.

Upstream `mkdud` commit used for the proof:

`173a908c5760f015886afe23879dcb93675bd7cf`

The generated update identifies itself as:

```text
Product:   openSUSE Tumbleweed
Installer: YaST
Name:      Desktop-Linux Snapshot20260930 installer layer
UpdateID:  92d2555c29130997
```

`mkdud --show` reports the unpacked-local-filesystem `OEMDRV` method as
supported for this update.
The same OEMDRV filesystem also carries `/autoinst.xml`. YaST/linuxrc's
OEMDRV convention is therefore used for both logical parts of the
Desktop-Linux layer:

```text
OEMDRV
├── autoinst.xml
└── linux/suse/x86_64-tw/
    ├── dud.config
    └── inst-sys/
        ├── .update.92d2555c29130997
        └── usr/...
```

The DUD is unpacked on the OEMDRV filesystem. It is not fetched as an
unsigned DUD archive during installation, so the archive-signature prompt path
is not the mechanism used by this candidate. Release integrity is established
independently from the source-controlled manifest and expected layer identity.
## Exact owned content

AutoYaST profile SHA-256:

`4dcf66e915763f2c6517decad477cbb35b5bbb84684d7dc8b99b05a6c80aece1`

Installer files:

- `/usr/bin/keyctl`:
  `a09d1ab9ecb5270d571ac92a703e7b10f976e5e42300a9a1e0a71386fb17429c`
- `/usr/lib64/libkeyutils.so.1.10`:
  `a16faea6d85e33aa6c3f10f293ed4b4b2d30faa1cee3be25ab9710fca510281e`
- `/usr/lib64/libkeyutils.so.1 -> libkeyutils.so.1.10`
- patched `autoyast_converter.rb`:
  `7ac0c97c6d3156f5093c85dce1a906c56c64e128fed2d9281ce4d5b9d7d02612`

The binaries/libraries are stock files from the same verified Snapshot20260930
DVD. No target-system package is replaced.
## Negative-gate layer artifact

Intermediate DUD:

`desktop-linux.dud`

Size: 35,009 bytes

SHA-256:

`cc3b71061868be72c2bb4964db1f13c23a1a07905f055b565e6e682a827d1699`

Combined local layer medium used for the negative gate:

`Desktop-Linux-Snapshot20260930-OEMDRV.iso`

Filesystem label: `OEMDRV`

Size: 526,336 bytes

SHA-256:

`942dc86d83608c63944e76e76ca3afd7e2735ae9da2455b571e9458541a2120f`
The layer root contains:

- `autoinst.xml`
- `BASE-ISO.sha256`
- `SOURCE-IDENTITY.txt`
- `SHA256SUMS`
- `SYMLINKS`
- the unpacked standard Tumbleweed/YaST DUD tree

Independent extraction of the finished OEMDRV ISO and
`sha256sum -c SHA256SUMS` returned OK for every listed file. Rock Ridge
read-back also preserved the `libkeyutils.so.1` symlink.

## VM proof state

Exactly one proof VM is registered for continued testing:

`Desktop-Linux-TW-Negative-20261002`

Its production-like provisioning configuration for the negative run was:

```text
SATA0  guard/internal VDI
SATA1  absent
SATA2  official Snapshot20260930 Offline ISO
SATA3  Desktop-Linux OEMDRV ISO
NIC0..3 disabled
EFI64 + TPM2 + Secure Boot enabled
```

The older duplicate proof VM was unregistered and its VM config deleted after
confirming that it no longer owned either proof VDI. No proof disk or shared
installation medium was deleted.

### Live OEMDRV discovery — PASS

The exact official Snapshot20260930 ISO booted with networking disabled and the
separate OEMDRV layer attached. AutoYaST automatically loaded the layer profile
and displayed its source-controlled prompts, including the distinct recovery
credential and TPM2 PIN questions.

Evidence:

- `evidence/oemdrv-autoyast-recovery-ask.png`
- screenshot SHA-256:
  `96623664d9fce26c341739ebbc3791f770843e01239fa2fca867425e1b600eb6`

This is live behavioral evidence that the separate OEMDRV layer is discovered
without repacking the upstream ISO or using network/host-side profile delivery.

### Absent-target fail-closed — PASS

For the destructive-safety negative run, the portable target VDI was detached
while the ASUS-like internal guard VDI remained attached.

Immediate pre-run guard VDI SHA-256:

`de1c73ea1d0c94d5c30caa571c8e4150ebfb2151fb879862f6619c5895b42fe9`

After the three AutoYaST asks, storage proposal stopped with the explicit
partitioning issue:

```text
Disk '/dev/disk/by-id/ata-PORTABLE_WORKSTATION_SSD_PORTABLETARGET000001'
was not found
```

The installer did not enter destructive installation.

Evidence:

- `evidence/absent-target-fail-closed.png`
- screenshot SHA-256:
  `421968b7ea5e253773ee207419fa816a0ec399216a80fdf4ce93c417d1e68e24`

After powering off the VM, the guard VDI SHA-256 was again:

`de1c73ea1d0c94d5c30caa571c8e4150ebfb2151fb879862f6619c5895b42fe9`

The before/after hashes are identical. Therefore the exact-target-absent path
failed closed and left the internal guard disk bit-for-bit unchanged.

The next live gate is the positive run on the same single VM with the exact
target VDI reattached.

## Offline NetworkManager target-write correction

A target-present offline run using the negative-gate layer reached the target
installation phase, then displayed a modal `No network running` error while
saving target settings.

Exact Snapshot20260930 `/usr/share/YaST2/modules/Lan.rb` has SHA-256:

`21147713babda7100843df42b8c8685156f3385bb65eaa00a280fbae19e1c429`

Its `Lan.Write` path contains:

```ruby
ensure_network_running if yast_config.backend?(:network_manager)
```

AutoYaST's target-chroot path deliberately invokes
`Lan.Write(apply_config: false)`: target configuration is being written, not
applied to the running installer. Requiring a live NetworkManager connection in
that path adds a 45-second wait and a modal error, breaking unattended offline
installation.

Changing the target backend to Wicked or `none` would change the product
outcome. The candidate therefore keeps NetworkManager and owns the smallest
version-specific installer-only correction:

```ruby
ensure_network_running if apply_config && yast_config.backend?(:network_manager)
```

Source patch:

`networkmanager-offline-write.patch`

SHA-256:

`c9dfaf137a0ae80ea7cb9fc7b9929d8369ae01a804a3d42c3c9814a5d3b49154`

Patched `Lan.rb` SHA-256:

`58231f7be60bfed86f44b8a5294c0bc405c8293da3939d407658bf76fe2535f0`

### Current patched layer candidate — static PASS

The layer was rebuilt through the same upstream `mkdud` + OEMDRV path.

Intermediate DUD:

- UpdateID: `1dbc2228122e6506`
- size: 43,390 bytes
- SHA-256:
  `73ad2ad177b0b4af5bd5e1e3279c7b4086e0c82ef0fe815768f4e005e3a9fa33`

OEMDRV ISO:

- filesystem label: `OEMDRV`
- size: 559,104 bytes
- SHA-256:
  `a5442f271181f85628327448be0ddfe87db588fe1dd14c326461e4f23dd70bd4`

Independent extraction of the completed ISO followed by
`sha256sum -c SHA256SUMS` returned OK for every owned file. Read-back of
`Lan.rb` contains the exact corrected condition above, and `autoinst.xml`
retains the observed target by-id.

### Target-present offline installation — storage/FDE PASS, boot gate exposed

The NetworkManager-corrected layer passed the earlier `No network running`
failure point. The target-present offline run wrote the target system and
reached boot-manager installation while the internal guard VDI remained
bit-for-bit unchanged.

Evidence:

- `evidence/positive-target-install-boot-manager-93.png`
  SHA-256 `dce616284513a301e2d64e7c582164749f2c70d9d70b329da8ff264bbf90e3f1`;
- `evidence/positive-storage-readback.txt`
  SHA-256 `e57938d6bab0ee5ad7552229b60275502c586a04bc704d47b7d49eb834f0c7f2`.

Powered-off target read-back proves:

- GPT with a 1 GiB ESP, encrypted root and encrypted swap;
- LUKS2 root with an Argon2id owner-passphrase keyslot;
- a `systemd-tpm2` token using keyslot 2;
- `tpm2-pin=true` and `tpm2-pcrlock=true`;
- installed initrd `rootfstype=btrfs` with `rd.driver.pre=btrfs`;
- root `@/.snapshots/1/snapshot` plus a post-install Snapper BLS entry for
  `@/.snapshots/2/snapshot`;
- `cr_root` and `cr_swap` with `tpm2-device=auto` in the installed initrd;
- sdbootutil PCR-lock metadata on the ESP.

This is direct installed-artifact proof of the frozen
`LUKS2 -> Btrfs/Snapper` storage architecture. There is no LVM layer.

### Removable fallback boot — FAIL, product gap isolated

With both installer media detached, Secure Boot enabled and only guard + target
disks present, firmware loaded an EFI payload from the target. The guest then
reset and repeated the cycle.

Evidence:

- `evidence/portable-fallback-reset.txt`
  SHA-256 `dc7136717f6c625d3ecc379eaf47392575bc37487cc5ca2f63e36e0b46fca5f5`.

The guard VDI remained bit-for-bit unchanged. The complete `Boot*` NVRAM
inventory was also byte-identical before and after the boot attempt; no named
openSUSE OS entry was created.

The installed ESP has:

```text
/EFI/BOOT/BOOTX64.EFI == shim.efi
/EFI/BOOT/grub.efi     absent

/EFI/systemd/shim.efi  present
/EFI/systemd/grub.efi  present
```

Exact Snapshot20260930 `sdbootutil` supports `--portable`; that mode switches
`esp_dst` to `/EFI/BOOT`, installs the second-stage bootloader as
`/EFI/BOOT/grub.efi`, and suppresses EFI-variable updates.

Exact `yast2-bootloader-5.0.42-1.1` does not expose this mode:
`Bls.install_bootloader` always invokes only `sdbootutil install`.
`update_nvram=false` therefore prevents owned NVRAM mutation but does not by
itself request the complete removable-media layout.

Candidate installer-only correction:

`systemd-boot-portable-layout.patch`

SHA-256:

`7fb66439ff2faa7f6893280329d4705f911b24035034c34406b8fab1540429ff`

It is bound to the exact YaST package. It only:

- allows `Bls.install_bootloader` to pass stock `sdbootutil --portable`;
- requests that portable mode for systemd-boot initial installation when
  `update_nvram == false`.

Exact identities:

- `bls.rb` original:
  `8e3fe14b84a645ef33352586baaefc02561e78a7e2a0e05e171b5ee977ea4743`;
- `bls.rb` patched:
  `7804641bb3e13a60e6dafeb672110b9e22281792535455c124f601f02d1b4967`;
- `systemdboot.rb` original:
  `331c55a9575f86bf610c12e7e4dda9348b010b1cfda0264d5f9f4eb9b8bc5d58`;
- `systemdboot.rb` patched:
  `201c3417bcc02d91804061125dad8dd1092c1be6b747d239dca220f945f3cc97`.

Deletion condition: remove this correction when upstream YaST can
declaratively request sdbootutil's supported portable/removable installation
mode for the no-NVRAM systemd-boot outcome.

### Portable-layout OEMDRV — static PASS

The small layer was rebuilt from source commit
`cbce132b10a34085c73d642c770a1e0727ae8c95` without rebuilding the upstream
4.4 GiB ISO.

- DUD UpdateID: `3fbebde260770b42`
- DUD size: 46,728 bytes
- DUD SHA-256:
  `ebffc4db553f054f8eb6ea014fef9b0fdc0cf0325ea269266f40bb03c91cd8f0`
- OEMDRV ISO size: 577,536 bytes
- OEMDRV ISO SHA-256:
  `bf4c1a103a28ca409523ef5b8670f7d33fbc7790d657b85c58a78e7da704ad54`

Finished-ISO extraction plus `sha256sum -c SHA256SUMS` passed for every owned
file. Read-back confirms the exact patched `bls.rb` and `systemdboot.rb`, all
prior installer corrections, the expected AutoYaST profile, and the preserved
libkeyutils symlink.

The next gate is repeating the target-present offline install with this layer
on the same single proof VM, then requiring `/EFI/BOOT/grub.efi` before the
installed-target cold boot.