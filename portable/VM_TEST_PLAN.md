# VirtualBox proof execution plan

## Purpose

This document defines the test harness and execution order for the single
`Desktop-Linux` VirtualBox proof VM.

It exists to prevent test execution from degenerating into screen polling,
blind keyboard input, indefinite waiting, or ad-hoc VM reconfiguration.

The architecture under test is frozen in `ARCHITECTURE.md`. This plan changes
only how the VM is observed and controlled.

## Authoritative harness rules

1. **Exactly one registered proof VM.**
   No clones, disposable copies, or additional proof VMs are created.
2. **No VirtualBox snapshots for proof state.**
   TPM/NVRAM/disk evidence is collected from the real single-VM state.
3. **NICs stay disabled during provisioning proof.**
   Serial transport is a VirtualBox host-control channel, not guest networking.
4. **Serial is the primary installer progress channel.**
   Screenshots are corroborating evidence only; a black or unchanged screenshot
   is never interpreted as progress.
5. **Every run starts powered off and unlocked.**
   Attachments, firmware, TPM, Secure Boot, NIC state, NVRAM and disk hashes are
   read back before launch.
6. **Every run has explicit stop conditions.**
   `Running` by itself is not progress.
7. **No product/architecture change is made to improve observability.**
   Diagnostic boot arguments are test-harness inputs and do not become the
   production boot configuration.

## Primary observability channel

Oracle VirtualBox exposes a standard 16550A-compatible virtual UART. In
this WSL/Windows harness configure:

```text
COM1
I/O base 0x3f8
IRQ 4
UART 16550A
host mode RawFile
host path \\wsl.localhost\runner02\home\github-runner\.cache\desktop-linux\vbox-proof\<run>-serial.log
```

VirtualBox writes the raw UART byte stream directly into the WSL proof cache.
This avoids guest networking and the WSL-to-Windows TCP/firewall boundary.
VirtualBox TCP serial is supported by the product but is not used by this
harness because the Windows-host TCP endpoint was not reachable from WSL during
Gate 0 validation.

The exact Snapshot20260930 ISO GRUB configuration prints:

```text
Please press 't' to show the boot menu on this console
```

and defines a hidden `t` hotkey that switches GRUB output to the serial
console. Installer boots therefore use this deterministic sequence:

1. press `t` and require the complete GRUB menu to appear in the UART log;
2. press `e` and require the edit buffer to appear in the UART log;
3. append `console=ttyS0,115200 textmode=1` to the exact kernel line;
4. reconstruct the ANSI terminal screen and verify the edited kernel line;
5. only then press Ctrl+X.

SUSE documents `console=ttyS0` as the headless AutoYaST serial-console path
and `textmode=1` as the text YaST path.

This boot-line modification is allowed for installer observability only. It is
not evidence for the installed-system measured-boot command line.

## Secondary evidence channels

For every gate collect, as applicable:

- VirtualBox machine state and session state;
- exact medium attachments and SATA port identities;
- EFI64, TPM2 and Secure Boot settings;
- all `Boot*` NVRAM variables before and after the run;
- VBox log;
- guard VDI SHA-256 before and after;
- target VDI SHA-256 before and after;
- powered-off GPT/LUKS/ESP read-back;
- screenshot only at named milestones or errors.

## Stall rule

A run is considered stalled when **both** conditions hold:

- no new serial-console event relevant to the current gate for 5 minutes; and
- no target-disk write activity for 5 minutes.

A stalled run is stopped and analyzed. It is never allowed to remain running
merely because VirtualBox reports `Running`.

Early boot has a stricter harness timeout: serial output must appear within
2 minutes after kernel launch when diagnostic serial boot arguments are active.

## Test credentials

VM proof uses throwaway credentials that are not production credentials.

They are stored only in the local proof cache with mode 0600 and are not
committed to git. The same credentials are reused across a single proof cycle
so recovery-passphrase, TPM-PIN and root-login behavior can be tested
deterministically.

## Gate 0 — harness sanity

Preconditions:

- one registered VM;
- VM powered off and session unlocked;
- COM1 RawFile serial configured exactly as above;
- NIC0..3 disabled;
- EFI64 + TPM2 + Secure Boot enabled.

Procedure:

1. remove the previous run's serial file;
2. attach the official Snapshot20260930 ISO and current OEMDRV layer;
3. start the VM;
4. press `t` and require the serial GRUB menu;
5. press `e` and require the serial edit buffer;
6. append and verify `console=ttyS0,115200 textmode=1`;
7. press Ctrl+X only after the reconstructed terminal screen confirms the
   expected kernel line.

PASS:

- serial transcript shows kernel output, linuxrc, installation-system loading,
  YaST startup and the source-controlled AutoYaST recovery-credential ask within
  the timeout.

FAIL:

- any required serial milestone is absent within its timeout.

Gate 0 passed live on 2026-10-02. The proof transcript reached:

```text
openSUSE Tumbleweed installation program v9.6
Loading Installation System (1/6) ... (6/6)
starting yast...
*** Starting YaST ***
Portable workstation recovery credential
Enter the LUKS recovery passphrase
```

No provisioning credential was entered during Gate 0.

No provisioning gate is run until Gate 0 passes.

## Gate 1 — absent-target destructive safety

Already proven. Rerun only if the target-selection/profile mechanism changes.

Inputs:

- guard disk present;
- portable target absent;
- official ISO + current OEMDRV;
- NICs disabled.

PASS:

- AutoYaST loads from OEMDRV;
- exact target is reported missing;
- destructive installation does not start;
- guard SHA-256 is bit-for-bit unchanged.

## Gate 2 — positive offline provisioning

Inputs:

- guard disk on SATA0;
- exact portable target on SATA1;
- official ISO;
- current portable-layout OEMDRV;
- NICs disabled;
- known throwaway recovery passphrase, TPM PIN and root password.

Procedure:

1. capture guard/target/NVRAM baselines;
2. boot via Gate-0 serial method;
3. answer the three AutoYaST questions over the serial console;
4. require visible serial milestones through storage proposal, package install,
   target configuration and bootloader installation;
5. expect the AutoYaST final-halt outcome;
6. power off only after a final-halt/error milestone or a defined stall.

PASS requires all of:

- guard VDI unchanged;
- target VDI changed;
- GPT has ESP + encrypted root + encrypted swap as product-generated;
- root is LUKS2 with owner-passphrase keyslot;
- TPM2 token has PIN and PCR-lock metadata;
- installed root declares Btrfs;
- Snapper/BLS snapshot entries exist;
- `/EFI/BOOT/BOOTX64.EFI` exists;
- **`/EFI/BOOT/grub.efi` exists**;
- no named openSUSE OS boot entry is added to NVRAM.

## Gate 3 — installed-target cold boot

Preconditions:

- Gate 2 PASS;
- installer ISO and OEMDRV detached;
- only guard + portable target remain;
- Secure Boot + TPM2 remain enabled.

First run is the production-like boot and does not alter the installed kernel
command line.

PASS requires:

- firmware reaches the removable fallback path without an installer medium;
- shim/second-stage/BLS boot succeeds;
- exactly one interactive TPM2 PIN entry is sufficient for the whole normal
  boot path; root unlock establishes the credential cache and encrypted swap
  must not prompt separately;
- installed root reaches userspace;
- no persistent named openSUSE NVRAM entry is required;
- guard remains unchanged.

If display observability is insufficient, do not type blindly. Stop and run a
separate diagnostic boot.

## Gate 3D — diagnostic installed boot

This gate diagnoses Gate 3; it does not replace it.

A temporary diagnostic BLS entry may add serial/status kernel arguments. Because
that changes the measured command line, TPM auto-unlock is expected not to be
proof-equivalent. Use the known owner recovery passphrase for this diagnostic
path.

After diagnosis, restore the original ESP/BLS bytes before re-running Gate 3.

## Gate 4 — installed storage/state inspection

Use either a successfully booted installed system or the official ISO rescue
environment over serial. Do not infer Btrfs state only from filenames.

Verify directly:

- `findmnt /` reports Btrfs;
- `btrfs subvolume list` shows the supported Tumbleweed layout;
- Snapper root configuration and snapshots exist;
- persistent user/application state is outside normal root rollback;
- there is no LVM layer.

## Gate 5 — boot trust and portability

Verify separately:

- Secure Boot on;
- normal TPM2+PIN unlock with exactly one PIN entry across root and swap;
- owner-passphrase recovery unlock with exactly one passphrase entry across
  root and swap;
- measured-state change prevents the normal TPM unlock path;
- fallback removable boot works;
- BootOrder/BootNext are not owned or persistently mutated by provisioning.

## Gate 6 — update/rollback behavior

Only after Gates 0–5 pass:

- `transactional-update dup` creates a new Btrfs snapshot;
- failed transaction does not become active;
- userspace-only success uses the intended soft-reboot path;
- kernel/harder success uses full firmware reboot;
- kexec is disabled;
- rollback restores system/root state without rolling back persistent user state.

## Execution discipline

For each new live result:

1. save transcript/log/hash/read-back evidence;
2. update `VM_PROOF.md` / provisioning proof documents;
3. read back against Product First and Economy First;
4. commit;
5. synchronize to GitHub;
6. add an issue #1 checkpoint for a materially new gate result.

No next gate begins while the current gate has an unexplained failure.