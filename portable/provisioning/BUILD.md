# Building the Desktop-Linux provisioning layer

## Canonical inputs

The release model is the verified official openSUSE Tumbleweed
Snapshot20260930 Offline ISO plus a separately verifiable Desktop-Linux OEMDRV
layer. The upstream ISO is not repacked for routine development.

Canonical source-controlled layer inputs:

- `autoinst-vm-proof.xml` — the only active AutoYaST profile;
- `systemd-fde-autoyast-authentication.patch` — preserves the selected
  systemd-FDE authentication mode for the explicit encrypted target;
- `systemd-boot-update-nvram.patch` — retains
  `update_nvram=false`;
- `networkmanager-offline-write.patch` — permits offline target config
  writes without requiring a live NetworkManager connection;
- `systemd-boot-portable-layout.patch` — requests stock sdbootutil
  portable/removable layout when NVRAM updates are disabled;
- stock `keyctl` and libkeyutils from the same verified DVD;
- `installer-overlay-manifest.txt`.

The canonical AutoYaST storage graph is explicit:

```text
GPT
├── EFI System Partition
└── outer LUKS2 (systemd_fde, Argon2id)
    └── LVM VG system
        ├── root LV -> Btrfs
        ├── home LV -> XFS
        └── swap LV
```

No second AutoYaST storage architecture is retained in the working tree.

## Build rule

A layer build must:

1. parse and validate the canonical AutoYaST profile;
2. start from clean Snapshot20260930 installer/runtime files whose SHA-256
   identities are pinned by the builder;
3. fail closed if any stock source file is missing or differs from the pinned
   Snapshot identity;
4. apply all four source-controlled installer patches from scratch, with no
   prepatched OEMDRV/cache tree as an input;
5. place `autoinst.xml` at OEMDRV root and installer updates under the
   standard YaST DUD tree;
6. build the small OEMDRV artifact;
7. record the profile hash, aggregate patchset hash, each patch hash and built
   artifact identity before VM boot.

The old `layer/oemdrv-portable-root` is not a builder input. It may remain only
as historical/live-proof evidence. The clean source cache is
`tools/snapshot20260930-instsys-source`; the builder verifies every consumed file
by SHA-256 before applying any patch. If that cache is absent or inconsistent,
the builder verifies the official Snapshot20260930 ISO SHA-256, extracts the
five pinned RPMs directly from that ISO, reconstructs the seven stock installer
files, verifies their pinned SHA-256 identities, and only then applies patches.
The full ISO hash is therefore paid only on cold/recovery rebuilds, not every
normal iteration.

The VM harness rebuilds only this small layer during iteration. Networking
remains disabled during provisioning proof.

Each built OEMDRV contains `SOURCE-IDENTITY.txt`, `SHA256SUMS` and `SYMLINKS`.
After ISO creation the builder extracts the ISO again and verifies the complete
regular-file hash set and symlink inventory before publishing it as the current
artifact. The external ISO SHA-256 is then recorded in `current-build.txt`.

This is a reconstructible and self-verifying build, not a promise of
byte-for-byte identical ISO bytes across runs: build IDs and filesystem/ISO
metadata may differ between otherwise equivalent builds.

## Local credential rule

Credential values are not source-controlled inputs. The VM proof keeps them
only in the local proof cache. When the OEMDRV is built, the builder renders a
runtime `autoinst.xml` from the canonical template:

- present recovery and root credentials are inserted into the runtime profile
  and their AutoYaST questions are removed;
- the generated DUD always carries
  `linux/suse/x86_64-tw/inst-sys/etc/desktop-linux-tpm2-pin` with mode `0600`;
  it contains the embedded PIN when present and is an empty placeholder when
  the PIN must be asked interactively;
- the documented DUD installation-system overlay exposes that file to YaST as
  `/etc/desktop-linux-tpm2-pin`, with no pre-script bridge;
- for the interactive case, the AutoYaST TPM question uses the native `<file>`
  element to overwrite that existing `0600` file; no `$VAL` secret-handling
  script is used;
- immediately before enrollment, the bootloader code exports the file content
  as the current `sdbootutil-tpm2-pin` key while keeping the recovery secret in
  `sdbootutil-recovery-pin`;
- any other missing value keeps its normal AutoYaST question.

The runner and keyboard layers never read or type credential values. The source
tree contains only the injection mechanism, never the values themselves.

`bench.py check` is a static-only validation path. It does not contact or
start VirtualBox; it checks source/storage invariants, all eight
present/missing credential combinations on temporary runtime profiles, and the
complete installer patchset against the pinned clean Snapshot sources. All four
patches must apply without rejects and the five modified YaST files must match
pinned post-patch SHA-256 identities exactly.

## Observability rule

Every autonomous run owns a directory under `vmbench/runs` in the proof
cache. VirtualBox COM1 writes directly to that run's `serial.log` and AutoYaST
streams YaST `y2log` into COM1 from the pre-script. A failure is therefore
diagnosable from host files without screenshots or later guest access.

## Promotion gate

The layer is not promoted until the autonomous VM run proves exact-target
safety, the accepted LUKS2->LVM storage graph, boot artifacts, unchanged guard
disk and no persistent owned NVRAM dependency.
