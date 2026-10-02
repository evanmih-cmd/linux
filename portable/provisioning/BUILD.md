# Building the Desktop-Linux provisioning layer

## Purpose

The production build unit is the **small Desktop-Linux provisioning layer**,
not a repacked Tumbleweed DVD.

The installation inputs are logically:

```text
verified official openSUSE Tumbleweed Snapshot20260930 Offline ISO
+
Desktop-Linux provisioning layer
```

VirtualBox presents them as two media. The final writable USB device co-locates
them after the verified ISO is written with Rufus or an equivalent image
writer.

## Immutable upstream base

File:

`openSUSE-Tumbleweed-DVD-x86_64-Snapshot20260930-Media.iso`

Required SHA-256:

`0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99`
The checksum metadata establishing this identity was verified with the
openSUSE Project Signing Key fingerprint:

`AD485664E901B867051AB15F35A2F86E29B700A4`

Do not construct or test a layer against a different ISO while claiming this
snapshot identity.

## Source-controlled layer inputs

The layer is defined by:

- `autoinst-vm-proof.xml`;
- `systemd-boot-update-nvram.patch`;
- stock `/usr/bin/keyctl` from the exact Snapshot20260930 DVD;
- stock `/usr/lib64/libkeyutils.so.1.10` and symlink from that DVD;
- the patched installer-only
  `/usr/share/YaST2/lib/bootloader/autoyast_converter.rb`;
- `installer-overlay-manifest.txt`, expanded into the complete layer manifest
  once the local-media transport format is finalized.

Current AutoYaST profile SHA-256:

`4dcf66e915763f2c6517decad477cbb35b5bbb84684d7dc8b99b05a6c80aece1`

Current fixed target identity:

`/dev/disk/by-id/ata-PORTABLE_WORKSTATION_SSD_PORTABLETARGET000001`
Current installer-only stock-file identities:

- `keyctl`:
  `a09d1ab9ecb5270d571ac92a703e7b10f976e5e42300a9a1e0a71386fb17429c`;
- `libkeyutils.so.1.10`:
  `a16faea6d85e33aa6c3f10f293ed4b4b2d30faa1cee3be25ab9710fca510281e`;
- patched `autoyast_converter.rb`:
  `7ac0c97c6d3156f5093c85dce1a906c56c64e128fed2d9281ce4d5b9d7d02612`.

## Layer build rule

Routine development must not rebuild the 4.4 GiB upstream ISO.

A layer build must:

1. validate `autoinst-vm-proof.xml` against the exact Snapshot20260930
   AutoYaST Relax NG schema;
2. extract any stock installer file only from the verified upstream ISO;
3. apply the source-controlled YaST correction to that exact installer version;
4. construct the smallest supported local-media payload that lets the
   Snapshot20260930 installer discover `autoinst.xml` and the installer update;
5. generate a complete manifest of every layer file, including size and
   SHA-256;
6. verify the built layer against that manifest before VM boot.
The exact supported local-media transport is part of the current live proof.
Once proven, its format and creation command become normative here.

## VirtualBox deployment

Attach:

```text
optical:
  verified official Snapshot20260930 ISO

small local medium:
  Desktop-Linux layer
```

Networking remains disabled for provisioning proof.

The VM arrangement intentionally keeps the two trust layers separate even
though the production USB will contain both on one writable physical device.

## Physical USB deployment

The release procedure is:

1. verify the downloaded official ISO using its signed checksum metadata and
   expected SHA-256;
2. write that already verified ISO to the USB device with Rufus or an
   equivalent image writer;
3. add the exact release Desktop-Linux layer to the same writable USB device;
4. verify the layer from its release manifest;
5. boot and perform the physical-host validation gates.
No requirement says that the whole USB device must retain the ISO's SHA-256
after the custom layer has been added. The security identities are the verified
upstream ISO and the independently verified custom layer.

## Historical derived-ISO proof

Earlier development repacked the upstream ISO with `mkmedia --initrd` /
`--instsys`. That work remains useful evidence that the profile and installer
files can be composed and that package payloads/UEFI image were preserved.

It is **not** the normal production build loop anymore. See `PROOF.md` for
that historical evidence.

## Promotion gate

The two-layer delivery model becomes proven only when the VM demonstrates:

- local discovery of the AutoYaST profile with networking disabled;
- application of the installer-only update layer;
- fail-closed behavior when the exact target is absent;
- unchanged internal guard disk;
- successful target-only installation when the target is present;
- no-NVRAM behavior, fallback ESP artifact, FDE/TPM/passphrase behavior and
  Secure Boot as specified by `../VM_PROOF.md`.