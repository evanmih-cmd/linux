# Rebuilding the Snapshot20260930 proof media

## Scope

This procedure rebuilds the provisioning proof image from the immutable
openSUSE Tumbleweed Snapshot20260930 Offline Image. It is a media-construction
procedure, not target-system runtime code.

The target-system packages remain the stock DVD packages. The only custom
owned inputs are the AutoYaST profile and the two-line installer-only
systemd-boot AutoYaST import correction.

## Immutable input

Input image:

`openSUSE-Tumbleweed-DVD-x86_64-Snapshot20260930-Media.iso`

Required SHA-256:

`0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99`

Do not build if that digest does not match.

The checksum metadata used to establish that digest was previously verified
with the openSUSE Project Signing Key fingerprint:

`AD485664E901B867051AB15F35A2F86E29B700A4`

## Builder

Use stock openSUSE `mkmedia` 6.3. The proof used git commit:

`dc56f31df44bee0d7d71d513614794abdb107e2b`

A rootless WSL proof can use unpacked host dependencies and a copy of
`mkmedia` whose only local changes select those host-tool paths. Those
changes are build-host convenience only and are not part of the media design.

## Source-controlled inputs

- `autoinst-vm-proof.xml`
  - SHA-256 `cecec02c055aba15c08281fe821472f36a8e2b5a8c076a8a4aa38389c3608968`
- `systemd-boot-update-nvram.patch`
  - SHA-256 `931e7ef8f3f4c877ef6e192c7fccb949209fefba0c23ce6dcf55de40f04b4c9f`

Validate the profile against the Snapshot20260930 AutoYaST
`profile.rng` before building.

## Installer-root stock inputs

Read these from the same verified DVD:

- `/usr/bin/keyctl` from `keyutils-1.6.3-7.9.x86_64.rpm`
  - SHA-256 `a09d1ab9ecb5270d571ac92a703e7b10f976e5e42300a9a1e0a71386fb17429c`
- `/usr/lib64/libkeyutils.so.1.10` from
  `libkeyutils1-1.6.3-7.9.x86_64.rpm`
  - SHA-256 `a16faea6d85e33aa6c3f10f293ed4b4b2d30faa1cee3be25ab9710fca510281e`
Create the symlink:

`/usr/lib64/libkeyutils.so.1 -> libkeyutils.so.1.10`

Extract the stock
`/usr/share/YaST2/lib/bootloader/autoyast_converter.rb` from the exact
Snapshot20260930 installer root and apply
`systemd-boot-update-nvram.patch`.

The expected patched-file SHA-256 is:

`7ac0c97c6d3156f5093c85dce1a906c56c64e128fed2d9281ce4d5b9d7d02612`

The installer overlay must contain only:

```text
usr/bin/keyctl
usr/lib64/libkeyutils.so.1 -> libkeyutils.so.1.10
usr/lib64/libkeyutils.so.1.10
usr/share/YaST2/lib/bootloader/autoyast_converter.rb
```

Place `autoinst-vm-proof.xml` as `autoinst.xml` in a separate initrd
overlay directory.

## mkmedia invocation

With `$INPUT_ISO`, `$OUTPUT_ISO`, `$INITRD_OVERLAY`,
`$INSTSYS_OVERLAY`, and `$TMPDIR` bound to local paths, run:

```sh
mkmedia --no-mount-iso \
  --tmp-dir "$TMPDIR" \
  --initrd "$INITRD_OVERLAY" \
  --instsys "$INSTSYS_OVERLAY" \
  --initrd-config 'AutoYaST=file:///autoinst.xml' \
  --create "$OUTPUT_ISO" \
  "$INPUT_ISO"
```
Run the same command once with `--dry-run` before creating the image.
The canonical proof dry-run exited successfully after recognizing the
Snapshot20260930 repository, installer root, legacy boot path and UEFI boot
image.

## Verification gates

After the build:

1. Run `checkmedia`; both ISO SHA-256 and installation-partition SHA-256
   must be OK.
2. Extract the initrd append stream and verify that `autoinst.xml` hashes
   to the source-controlled profile and that
   `etc/linuxrc.d/61_mkmedia` contains
   `AutoYaST=file:///autoinst.xml`.
3. Extract `boot/x86_64/root` and verify the patched importer, `keyctl`,
   `libkeyutils.so.1.10`, and its symlink.
4. Verify `CHECKSUMS.asc` against `CHECKSUMS.key`.
5. Verify that the UEFI boot image equals the upstream image.
6. Compare SHA-256 manifests for every RPM under `/noarch` and
   `/x86_64`; the manifests must be identical.
7. Record the resulting external image SHA-256 in
   `installer-overlay-manifest.txt` and `PROOF.md`.

The canonical proof image produced on 2026-10-02 has SHA-256:

`c93d8d394b5e03d33fe880612f3ac346f60825871e1229e45718414f6d1765bb`

Its transient CHECKSUMS signing-key fingerprint is:

`A05F28065D477D6E6B223A5804301C8F5B6BA4AE`

## Reproducibility boundary

The procedure is repeatable, but the ISO is not expected to be byte-identical
across builds while `mkmedia` generates a new transient CHECKSUMS signing
key. Each accepted build therefore has its own external SHA-256 and transient
key fingerprint.

A fixed signing key could make that part deterministic, but it would create a
persistent key-management obligation. The current proof does not add that
cost because byte-identical rebuilds are not a business requirement; verified
input identity, controlled deltas, and repeatable validation are.

## Live-proof boundary

A successful media build is not proof that destructive installation is safe.
The candidate remains unpromoted until the two-disk VM gates in
`../VM_PROOF.md` prove absent-target failure, internal-disk non-modification,
target-only installation, FDE/TPM behavior, no-NVRAM bootloader behavior and
cold Secure Boot.