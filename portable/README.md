# Portable workstation

This directory contains the design and implementation artifacts for a
self-contained openSUSE Tumbleweed workstation carried on removable storage.

The workstation is intended for a narrow browser-centric sensitive workload. It
must keep its required system and persistent state on the removable device,
avoid taking ownership of the host's internal storage or persistent firmware
configuration, update before sensitive work begins, and remain recoverable by
the owner.

## Documents

- [Business requirements](BUSINESS_REQUIREMENTS.md) — authoritative product
  requirements. Technical implementation choices must serve these requirements.
- [Architecture](ARCHITECTURE.md) — current Tumbleweed architecture and its
  validation gates.
- [GitHub issue #1](https://github.com/evanmih-cmd/linux/issues/1) — research
  history, rejected alternatives, checkpoints, corrections, and current proof
  work.

## Current direction

The implementation direction is:

```text
openSUSE Tumbleweed
→ Agama unattended provisioning
→ removable SSD only
→ Secure Boot + systemd-boot/BLS
→ TPM2+PIN primary unlock + owner LUKS passphrase for emergency portability
→ LUKS2 + Btrfs/Snapper
→ mandatory transactional-update startup maintenance
→ soft reboot when sufficient; kexec disabled
→ sensitive workload released only after successful maintenance
```

The next proof stage is Oracle VirtualBox. Physical-host checks that cannot be
proved in a VM are explicitly listed in the architecture document.

## Repository principles

This project inherits the Factory architecture discipline even though it is
physically and infrastructurally independent from Factory:

- **Product first** — exhaust mature supported product capabilities before
  introducing custom mechanisms.
- **Economy first** — minimize implementation, operational, maintenance, and
  debugging cost.
- Custom code is residual glue only.
- Critical-path beta/preview/experimental functionality is treated as
  unavailable.
- Installer/tool limitations do not redefine the business requirements.
- Prefer a simpler supported product outcome over a technically elegant custom
  subsystem.

## Legacy files

`autoinstall-fresh.yaml` and `autoinstall-reinstall.yaml` are obsolete
Ubuntu/Subiquity experiments from the earlier design. They do **not** describe
the current architecture and must not be used for provisioning. They remain
temporarily as research history until the validated Agama profile replaces
them.
