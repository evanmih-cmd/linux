# Windows two-disk bench: real state and operator runbook

**Status (2026-10-09): manual Microsoft WinPE deployment reached Windows 11 desktop once; full acceptance remains BLOCKED.**
Three earlier stock Windows Setup attempts failed to create a working target-local boot path. Subsequently, the same two-disk VM was deployed manually with DiskPart, DISM, BCDBoot and REAgentC, using the common password-free XML for specialize/OOBE. The first Windows desktop was observed on the VM without a password prompt. Repeat logon, enabled WinRE, Windows-side disk Offline state and Secure Boot runtime are not yet proven. Current SOAP sees Running with black framebuffer after Shift; Guest Additions are not ready and an ACPI power-button request did not shut the guest down. No hard reset/reinstall has been made.

- Installed canonical VM `Desktop-Windows-11-Pro` and the
  `installed-clean` snapshot remain preserved.
- Existing separate acceptance VM `Desktop-Windows-11-Pro-TwoDisk`:
  SATA 0 = protected 8 GiB GPT SSD1 analog with preservation sentinel;
  SATA 1 = destination 96 GiB VDI. No SATA port swaps are allowed.
- One official Microsoft Windows 11 ISO; one common `Autounattend.xml`.
  No separate bench/product variants for disk targeting or installed OS.
- Human operator identifies the protected disk, sets it Offline in WinPE,
  independently identifies the destination by actual device and size,
  and enters each partition-changing command manually.
- **Absolutely no** `DiskPart /s`, automatic `clean` or formatting scripts,
  scripted DiskID selection, `.cmd`, `.bat` or PowerShell programs to
  partition the ASUS or bench.

## Previous real experiments

1. **Initial stock Setup:** Protected Disk 0 Offline; Windows Setup
   selected empty target Disk 1. Target GPT contained only MSR + NTFS.
   Boot servicing failed: `BFSVC 0x1F`, `0x8007001F`.
2. **Firmware BootOrder:** Existing `Boot0005` (target, SATA1) promoted
   ahead of `Boot0004` (protected, SATA0) using VirtualBox SOAP UEFI NVRAM
   `IUefiVariableStore_changeVariable`, not SATA port swaps. Persistence
   PASS, Secure Boot on; Windows Setup still enumerated protected as Disk 0
   and target as Disk 1. Setup again failed to create a target-local ESP.
3. **Precreated ESP on target:** Manually created 300 MiB ESP and 16 MiB
   MSR before choosing remaining unallocated target space in Setup.
   Setup created a *second* 200 MiB ESP. The result was two ESPs, which is
   not the approved layout, followed by `BFSVC: Failed to get system partition`,
   fatal `Update Boot Code` error `0x80073B92` at 00:02:34 on 2026-10-09.

Protected SSD1 GPT and sentinel stayed intact in these runs.
Neither firmware priority nor manually precreating *only* the ESP fixes
stock Setup's system-partition selection.

## Approved next run — manual-only Microsoft deployment

See **[manual deployment, DiskPart/GPT/WinRE 2 GiB commands](deployment/README.md)**,
the authoritative exact sequence.

- UEFI/GPT, **ESP 300 MiB → MSR 16 MiB → Windows NTFS →
  WinRE 2048 MiB, physically at disk end**.
- Explicit target ESP through `BCDBoot /s S: /f UEFI`; DISM applies the
  official Microsoft Windows 11 Pro image; REAgentC registers recovery.
- Every partition/format/cleanup command typed manually in interactive
  WinPE, after operator checks protected disk Offline and target identity.
- Same canonical XML for Windows specialize/OOBE; no automated disk wiping.
- Target-local ESP and BCD, independent physical-disk boot, WinRE,
  preservation of SSD1 and Secure Boot must be proven live.
- `BCDBoot /s` does not create a firmware NVRAM entry; Asus firmware
  presentation of the RAID LUN must be verified on physical hardware.

The same VM subsequently completed the manual deployment and first boot to the Windows desktop. WinPE AUDIT.CMD reported 29 PASS / 0 FAIL / 6 NOT_PROVABLE. A new read-only Linux/VDI parity audit sees 17 PASS / 0 FAIL / 6 NOT_PROVABLE_ENCRYPTED, including intact protected GPT/sentinel, target-local ESP/BCD, WinRE image and exact target partition geometry. The system VDI is now BitLocker-marked (`-FVE-FS-`), so the offline auditor cannot read its Windows files or REAgentC registration without recovery material. Because the VM was Running during parity, that evidence is provisional until a powered-off audit can be obtained. Do not claim full post-boot acceptance.

## Read-only bench commands

From `windows/vm/harness`:

```bash
python3 bench.py two-disk-status
python3 bench.py two-disk-verify
```

`two-disk-verify` requires the disposable VM to be PoweredOff.
The protected analog and target VDI are under
`~/.cache/desktop-windows-two-disk/vbox-bench/`.
The official ISO stays read-only. No VM-only disk-number shortcuts
may enter production.

## Sources

- [Microsoft UEFI/GPT partition layout](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/configure-uefigpt-based-hard-drive-partitions)
- [Microsoft CreatePartitions-UEFI example](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/oem-deployment-of-windows-desktop-editions-sample-scripts)
- [Microsoft capture and apply Windows, system, recovery](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/capture-and-apply-windows-system-and-recovery-partitions)
- [Microsoft BCDBoot reference](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/bcdboot-command-line-options-techref-di)
