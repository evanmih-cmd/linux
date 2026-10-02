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
## Built proof artifacts

Intermediate DUD:

`desktop-linux.dud`

Size: 35,009 bytes

SHA-256:

`cc3b71061868be72c2bb4964db1f13c23a1a07905f055b565e6e682a827d1699`

Combined local layer medium:

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

The existing `Desktop-Linux-TW-Proof` VM has been reconfigured to contain:

```text
SATA0  guard/internal VDI
SATA1  Desktop-Linux OEMDRV ISO
SATA2  official Snapshot20260930 Offline ISO
```

The portable target disk is absent for the next fail-closed run. All guest
NICs remain disabled.
Fresh pre-run SHA-256 of the powered-off guard VDI:

`de1c73ea1d0c94d5c30caa571c8e4150ebfb2151fb879862f6619c5895b42fe9`

This value is the immediate before-state for the negative test; the post-run
guard VDI must match it bit-for-bit.

The live boot result is not yet recorded here. Static layer construction and
read-back are PASS; automatic discovery/application and absent-target
fail-closed behavior remain live gates.