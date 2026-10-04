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
2. use only the verified Snapshot20260930 installer/runtime inputs;
3. apply only the source-controlled, version-bound installer corrections;
4. place `autoinst.xml` at OEMDRV root and installer updates under the
   standard YaST DUD tree;
5. build the small OEMDRV artifact;
6. record the profile/patch hashes and built artifact identity before VM boot.

The VM harness rebuilds only this small layer during iteration. Networking
remains disabled during provisioning proof.

## Local credential rule

Credential values are not source-controlled inputs. The VM proof keeps them
only in the local proof cache. When the OEMDRV is built, the builder renders a
runtime `autoinst.xml` from the canonical template:

- present recovery and root credentials are inserted into the runtime profile
  and their AutoYaST questions are removed;
- a present TPM PIN is written only into the generated OEMDRV and loaded by the
  AutoYaST pre-script into the stock `sdbootutil-tpm2-pin` keyring entry;
- any missing value keeps its normal AutoYaST question.

The runner and keyboard layers never read or type credential values. The source
tree contains only the injection mechanism, never the values themselves.

`bench.py check` is a static-only validation path. It does not contact or
start VirtualBox; it checks source/storage invariants and all eight
present/missing credential combinations on temporary runtime profiles.

## Observability rule

Every autonomous run owns a directory under `vmbench/runs` in the proof
cache. VirtualBox COM1 writes directly to that run's `serial.log` and AutoYaST
streams YaST `y2log` into COM1 from the pre-script. A failure is therefore
diagnosable from host files without screenshots or later guest access.

## Promotion gate

The layer is not promoted until the autonomous VM run proves exact-target
safety, the accepted LUKS2->LVM storage graph, boot artifacts, unchanged guard
disk and no persistent owned NVRAM dependency.
