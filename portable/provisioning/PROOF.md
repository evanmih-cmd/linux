# Snapshot20260930 provisioning-media proof

## Scope

This records the construction and static verification of the provisioning
candidate based on the immutable openSUSE Tumbleweed Snapshot20260930 Offline
Image. It does **not** promote the candidate into the architecture. The
two-disk live installation gates in `../VM_PROOF.md` are still required.

## Verified input

Input image:

`openSUSE-Tumbleweed-DVD-x86_64-Snapshot20260930-Media.iso`

SHA-256:

`0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99`

The signed checksum metadata for that immutable image was verified before the
proof build. The ISO was then independently checked against that metadata.

Exact relevant packages read from the image:

- `yast2-bootloader-5.0.42-1.1.x86_64`
- `yast2-storage-ng-5.0.50-1.1.x86_64`
- `autoyast2-5.0.10-1.1.noarch`
- `autoyast2-installation-5.0.10-1.1.noarch`
- `sdbootutil-1+git20260929.26b6989-1.1.x86_64`
- `keyutils-1.6.3-7.9.x86_64`
- `libkeyutils1-1.6.3-7.9.x86_64`

## Product behavior verified from the exact image

The Snapshot20260930 product control selects:

- `systemd-boot`;
- `systemd_fde`;
- `argon2id`;
- `tpm2+pin`;
- Btrfs root with snapshots.

The exact AutoYaST storage implementation:

- resolves fixed drive names through `find_by_any_name`;
- reports a fatal `NoDisk` issue when the fixed drive is absent;
- falls back to the normal guided proposal when the selected drive has no
  explicit partitions;
- restricts that guided proposal to the resolved drive names;
- performs AutoYaST destructive cleanup only for drives present in that map.

The media profile therefore owns target identity, not partition topology.
`general/storage/proposal/encryption_password` is supported by the exact
runtime but not by the Snapshot20260930 Relax NG `general/storage` schema.
The supported initial-stage AutoYaST ask mechanism is therefore used to add
that value to the in-memory profile after initial schema validation and before
the initial configuration is re-imported.

The exact `sdbootutil` prefers `%user:sdbootutil-tpm2-pin` over the deprecated
generic key used by current YaST. A second password-style AutoYaST question
places the normal boot PIN in that installer-kernel keyring entry, so the
owner LUKS passphrase and normal TPM PIN need not be the same value.

The exact installer squashfs does not contain `/usr/bin/keyctl`. The media
overlay therefore adds the stock `keyctl` binary and `libkeyutils.so.1` from
the same Snapshot20260930 DVD. They are installer-only files, not target
package replacements.

The exact `SystemdBoot#propose` forces `update_nvram=true`, and exact
`AutoyastConverter#import_systemd_boot` does not import the AutoYaST
`global/update_nvram` value. `systemd-boot-update-nvram.patch` is the minimal
installer-only correction.

## Profile and overlay evidence

`autoinst-vm-proof.xml` validates against the exact Snapshot20260930 AutoYaST
Relax NG schema.
Profile SHA-256:

`50298c8699b3baf6c44c3744ea7b65171d3431b10487d828dfa522886b0b973d`

The profile explicitly fixes English (`en_US`), US keyboard, `Europe/Berlin`
timezone with a UTC hardware clock, installs `sdbootutil`, and disables the
installer online-update step. This removes those installer-default choices
from the unattended proof while guest networking remains disabled externally.

The profile was read back from the second XZ/cpio initrd stream and had that
same hash. `/etc/linuxrc.d/61_mkmedia` in that stream contains exactly
`AutoYaST=file:///autoinst.xml`.

The patched `import_systemd_boot` method was read back from the built installer
root and contains only the required `update_nvram` import addition. Its
SHA-256 is:

`7ac0c97c6d3156f5093c85dce1a906c56c64e128fed2d9281ce4d5b9d7d02612`.

The built installation system contains:

- `/usr/bin/keyctl`;
- `/usr/lib64/libkeyutils.so.1.10`;
- `/usr/lib64/libkeyutils.so.1 -> libkeyutils.so.1.10`.

The rebuilt initrd contains the exact option:

`AutoYaST=file:///autoinst.xml`

## Final derived image

Canonical output image:

`openSUSE-Tumbleweed-DVD-x86_64-Snapshot20260930-DesktopLinuxProof-canonical.iso`

SHA-256:

`8b52870c107cb2b4516a22820c4af6cb02189de97630f650d38b48abe9517452`

`checkmedia` returned both ISO SHA-256 OK and installation-partition SHA-256
OK. The image has no whole-image signature; its external SHA-256 is the
identity of this local proof artifact.

Because installer files changed, stock `mkmedia` generated a transient build
key, recalculated `/CHECKSUMS`, embedded that public key into the media and
initrd, and signed the new `/CHECKSUMS`. The observed fingerprint is:

`001F4F7DA362FBA92459083509B5E87D2445E157`

Independent GPG verification of `CHECKSUMS.asc` against `CHECKSUMS.key`
returned both `GOODSIG` and `VALIDSIG` for that fingerprint.

Upstream and canonical `/CHECKSUMS` each contain the same 213 paths. Exactly
three recorded hashes changed: `boot/x86_64/root`,
`boot/x86_64/loader/initrd`, and the legacy BIOS
`boot/x86_64/loader/isolinux.bin`. Direct readback of the final
`isolinux.bin` differs from its recorded value because xorriso rewrites its
Boot Info Table during ISO layout. This does not affect the UEFI path used by
this proof.

The UEFI boot image is bit-for-bit identical to the verified upstream input:

`4204528acd3a61e862c5a983c0ad025e45b0c870016c45b27fa1db947f6ae638`

An independent extraction and SHA-256 comparison of every repository RPM
found identical manifests on upstream and canonical media:

- 1,252 noarch RPMs;
- 3,260 x86_64 RPMs;
- 4,512 RPMs total, with an empty manifest diff.

## Live-proof status

A VirtualBox 7.2.20 proof VM has been created with effective state read back as:

- EFI64 firmware;
- TPM 2.0;
- Secure Boot enabled;
- guest NICs disabled.

The ASUS guard VDI is attached first on SATA Port 0 with serial
`ASUSINTERNAL20260930`.

The portable target VDI exists in the proof cache but is intentionally not
attached yet, so the first installation run can exercise the required
absent-target failure path. Its planned serial is
`PORTABLESSD20260930A`.

There is no media-staging blocker. VirtualBox can open both the upstream and
derived ISOs directly through the existing WSL UNC namespace. The working
namespace is `\\wsl.localhost\runner02\...`; earlier failed staging checks used
the wrong distro name (`Ubuntu`). The existing proof VM already uses a
`runner02` UNC path for its optical medium, so no Windows-drive mount, WSL
interop, new share, firewall change, or other authority expansion is needed.

No VM provisioning gate is marked passed until the live absent-target and
two-disk installation tests run.