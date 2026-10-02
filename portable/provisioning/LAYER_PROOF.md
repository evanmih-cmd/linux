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

The next gate is a target-present offline installation using this patched layer
on the same single proof VM.