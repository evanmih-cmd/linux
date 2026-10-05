# Portable workstation — VirtualBox proof

`ARCHITECTURE.md` is the architecture source of truth.
`VM_TEST_PLAN.md` defines the execution procedure. This file defines the claims that
must be proven in VirtualBox.

## Proof boundary

The single proof VM models:

- SATA0: ASUS-like internal guard disk;
- SATA1: disposable portable target;
- SATA2: verified openSUSE Tumbleweed Snapshot20260930 Offline ISO;
- SATA3: current Desktop-Linux OEMDRV layer;
- NICs disabled during provisioning;
- UEFI + Secure Boot + TPM2;
- Linux graphics controller `VMSVGA`, at least 64 MiB VRAM
  (128 MiB by default), with 3D acceleration disabled unless a proof run
  explicitly enables and validates it;
- COM1 16550A in VirtualBox RawFile mode.

The proof target storage graph is exactly:

```text
GPT
├── EFI System Partition
└── outer LUKS2
    └── LVM VG system
        ├── root LV -> Btrfs/Snapper
        ├── home LV -> persistent /home
        └── swap LV
```

There is one cryptographic unlock boundary: the outer LUKS2 container.

## Evidence rule

A run is evidence only when the harness records it directly. Every autonomous
`bench.py run` writes its COM1 stream directly to
`runs/<run-id>/serial.log` from VM launch onward. AutoYaST streams the complete
YaST `y2log` into the same COM1 stream. The log therefore survives harness,
installer or VM failure up to the last byte VirtualBox wrote.

Each run also records host-side events, preflight identities, attachments,
guard/target hashes and NVRAM state. Serial/system-state evidence remains the
primary correctness evidence. SOAP framebuffer captures may be retained as
diagnostic evidence for graphical-session failures, but never replace the
service/session/process gates.

Proof credentials are local inputs, not repository content. Present values are
embedded only into the generated OEMDRV/runtime AutoYaST profile; absent values
remain ordinary AutoYaST prompts. The harness itself never types credential
values.

## Provisioning gates

1. The verified official ISO plus OEMDRV installs with guest networking
   disabled.
2. If the exact portable target is absent, destructive installation does not
   start and the guard disk remains bit-for-bit unchanged.
3. With the target present, storage is exactly ESP + one outer LUKS2 + LVM VG
   `system` with root/home/swap LVs.
4. Root is Btrfs with Snapper; home is persistent state outside normal root
   rollback; swap is an LV inside the same encrypted container.
5. The outer LUKS2 device retains an owner recovery passphrase and the normal
   TPM2+PIN path.
6. The removable ESP contains the complete fallback boot path, including
   `/EFI/BOOT/BOOTX64.EFI` and the required second-stage artifact.
7. Provisioning does not modify the ASUS-like guard disk and does not create a
   persistent owned openSUSE NVRAM boot dependency.
8. Installed-target cold boot succeeds through Secure Boot and requires only
   one cryptographic credential for the outer LUKS2 container.
9. The installed workstation reaches a KDE Plasma Wayland session as the
   ordinary `portable` user, with `kwin_wayland` and `plasmashell` running and a
   non-black framebuffer. Legacy `VBoxVGA` or undersized VRAM is a bench
   configuration failure, not an acceptable product result.

## Later system gates

After provisioning passes, validate Snapper rollback, transactional-update,
soft/full reboot policy, kexec-disabled policy and sensitive-workload gating.

VirtualBox cannot prove ASUS-specific firmware behavior or physical external
device compatibility; those remain physical-host gates.
