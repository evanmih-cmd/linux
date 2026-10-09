# Portable read-only WinPE acceptance audit

This is a **parallel** implementation of the Windows deployment checks. It
does not replace the existing Linux/VirtualBox VDI inspectors or
\`windows/vm/harness\`. It validates the exact manual deployment contract in
[../deployment/README.md](../deployment/README.md).

## Artifact and boundary

\`winpe-audit.exe\` is a standalone 64-bit Windows console binary (about 70
KiB) built using MinGW-w64, statically linked except for stock
\`KERNEL32.dll\`, \`ADVAPI32.dll\`, and \`msvcrt.dll\`. It runs directly in
the **stock Windows 11 installer WinPE** (\`Shift+F10\`), with no PowerShell,
Python, Guest Additions or network. Copy the EXE onto the USB installation
drive; keep the common \`Autounattend.xml\` unchanged.

**Disk safety:**

- Opens \`\\.\PhysicalDriveN\` using \`GENERIC_READ\`, shared access.
- Opens existing volume GUID paths and files using \`GENERIC_READ\`.
- Invokes only read-only \`bcdedit /store ... /enum all\` in WinPE and
  \`reagentc /info\` in booted Windows.
- Does **not** mount, offline, online, clean, format, create/delete, resize,
  write BCD, assign a letter, install drivers or select disks automatically.
- Does not write to any internal disk or partition. Redirect stdout to a USB
  path to retain a machine-readable test result.

Arguments require manually verified *current* physical disk numbers.
**Do not assume that target=1 and protected=0 outside our test bench.**

For the current VM, after manually selecting and checking the protected and
target disks:

\`\`\`cmd
I:\WINPE-AUDIT.EXE --target 1 --protected 0
\`\`\`

On the real ASUS, find the USB letter and the real physical disk numbers
using *interactive* \`diskpart\`, \`list disk\`, and \`detail disk\`. For
example, after determining those values, run:

\`\`\`cmd
U:\WINPE-AUDIT.EXE --target N --protected M --phase winpe > U:\winpe-audit.txt
\`\`\`

Replace \`N\` and \`M\` with the verified decimal disk numbers and \`U:\`
with the **USB** drive letter. This report redirection writes only to USB,
not either SSD. **Run after copying the one canonical XML into Panther,
before reboot**, to accept the offline portion of the deployment.

The utility's exit codes are **0** all evaluated checks passed with no
undetermined checks; **1** at least one FAIL; **4** no FAIL but at least one
NOT_PROVABLE; **2** invalid input or disk access error. Do **not** interpret
exit code 4 as global acceptance.

## Coverage

| Requirement of manual deployment | WinPE audit | After first boot |
| --- | --- | --- |
| Correct physical destination / protected disk Offline | Physical disk numbers and IOCTL Offline state | Reconfirm Offline |
| Valid UEFI GPT and backup, exactly one ESP | Reads raw primary+backup GPT, CRC32 | Same |
| ESP 300 MiB, MSR 16 MiB | Partition type GUID, exact size and order | Same |
| Windows occupies remainder | Exact physical partition offsets, contiguous | Same |
| Recovery exactly 2048 MiB *last* | GPT Recovery GUID, attributes, <=1 MiB tail alignment | Same |
| ESP FAT32 / Windows+Recovery NTFS | Raw filesystem boot sector inspection | Same |
| ESP EFI/BCD target-local | GUID volumes mapped to target physical offset, EFI MZ, BCD regf; stock \`BCDEdit\` validates OS loader entries | Same |
| DISM-applied Windows image | \`ntoskrnl.exe\`, \`winload.efi\`, SYSTEM hive, PE/regf header | Live edition from Windows API |
| \`Winre.wim\` exists on correct Recovery volume | Matches target GUID/offset and WIM magic | Same |
| \`REAgentC /setreimage\` registered expected WinRE | Installed \`ReAgent.xml\` must point to target GPT GUID+partition offset | \`reagentc /info\` must report Enabled |
| One canonical answer file | \`Panther\Unattend.xml\` has specialize/OOBE, no disk wipe directives; compare bytes with attached original \`Autounattend.xml\` | Installed file rechecked; byte comparison NOT_PROVABLE if original media absent |
| Protected disk unchanged | GPT CRC, Offline; optional old synthetic-VDI sentinel or full-disk SHA-256 reference | Repeat |
| Independent boot and Secure Boot | **NOT_PROVABLE** prior to actual boot | Booted OS volume must map to target, protected disk Offline; Secure Boot registry must be enabled |
| Firmware exposes RAID LUN on ASUS | **NOT_PROVABLE in a VM** | Physical ASUS-specific acceptance, not spoofed by VM |

\`NOT_PROVABLE\` is deliberate, never rewritten as PASS. Neither an
unpowered/offline audit nor a VirtualBox test proves the ASUS firmware's
physical RAID LUN Boot Menu behavior.

### Pre-install protected SSD preservation baseline

For **cryptographic evidence that the original SSD1 data did not change**,
record its full raw SHA-256 *before* installing (read-only but potentially
time-consuming on large disks):

\`\`\`cmd
U:\WINPE-AUDIT.EXE --target N --protected M --hash-protected > U:\before.txt
\`\`\`

Save the printed \`PROTECTED_DISK_SHA256\` outside the disk under test. On
the post-install run, provide that 64-character digest:

\`\`\`cmd
U:\WINPE-AUDIT.EXE --target N --protected M --expected-protected-sha256 HEX > U:\after.txt
\`\`\`

Without a trusted **pre-install** reference, \`protected.byte_preservation\`
correctly reports NOT_PROVABLE; a valid current GPT alone is not evidence
that every byte of SSD1 has been preserved. A baseline computed *after* the
installation is not a valid pre-install baseline.

The disposable VM has a pre-install synthetic sentinel; to verify it using
the *same portable EXE* add \`--sentinel-lba 567297\` and
\`--sentinel-sha256 61e04e0db0c910591ec25df07c1b40d33b6d3d6cca28fadce301f1f1fde76ebb\`
(bench-only, not applicable to ASUS).

## After first boot

Copy the same EXE to the installation USB. In the installed Windows Pro
administrator terminal, determine disk numbers again and run:

\`\`\`cmd
U:\WINPE-AUDIT.EXE --target N --protected M --phase booted > U:\booted-audit.txt
\`\`\`

The booted phase checks that the running Windows system volume is actually
on the target disk, while protected SSD1 is Offline; checks the real OS
Professional SKU, UEFI Secure Boot and enabled WinRE. Real ASUS Boot Menu
selection still requires observing the firmware and physical disk behavior.

## Parallel, independent Linux/VDI parity

The legacy Linux inspectors and VirtualBox harness remain untouched.
\`parity.py\` independently reads the VDI and checks the overlapping disk,
file, BCD header, Recovery/REAgent and answer XML facts. It never launches
or changes the VM:

\`\`\`bash
PYTHONPATH=~/.cache/desktop-windows/diag-libs \
  python3 windows/vm/winpe-audit/parity.py \
  --bench ~/.cache/desktop-windows-two-disk/vbox-bench
\`\`\`

Copy the Windows auditor's text report from an attached USB drive and add
\`--winpe-report <path>\` to compare **matching check IDs automatically**.
Differences fail the parity command. Cross-environment-only checks, such as
IOCTL Offline state and firmware Secure Boot, are evaluated in their
respective environments, not fabricated in the other environment.

**Live 2026-10-09 result (FINAL binary on the real two-disk WinPE VM):**
**38 PASS / 2 FAIL / 5 NOT_PROVABLE**, including bench-specific
pre-install sentinel PASS. The two failures are exactly the absent
`Panther\Unattend.xml` and its therefore-unprovable byte identity; both
are expected until the operator completes step 4 of deployment.
Windows BCD is parsed by stock BCDEdit (PASS), and the WinRE registration
points at the physical recovery GPT GUID/offset (PASS).
The parallel host-side independent Linux/VDI parser finds
**21 PASS / 2 FAIL** for its 23 supported facts: the same layout, files,
registration and absent XML, with no contradictory factual result.
Those Linux tests do not replace WinPE tests and do not purport to inspect
physical WinPE Offline status or booted Secure Boot.
**No booted Windows Pro acceptance is claimed yet.**

**SHA-256 of checked-in `winpe-audit.exe`:**
`0ce205fcc3207cc0ad28405766f279d0d1975fc9d7ba166be16656acba908cbb`.

## Rebuild from source

The checked-in EXE is immediately usable; the C source is included for
auditability. With MinGW-w64 installed on Linux:

\`\`\`bash
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
  -o winpe-audit.exe audit.c -ladvapi32 -static -s
\`\`\`

Confirm system-only imports (\`KERNEL32\`, \`ADVAPI32\`, \`msvcrt\`) via
\`objdump -p winpe-audit.exe\`. No custom WinPE ISO or PowerShell optional
component is required.
