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
4. **Serial is the mandatory installer progress and diagnostic channel.**
   COM1 writes directly into the current run directory from VM launch onward.
   Correctness and diagnosis never depend on screenshots.
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
host path \\wsl.localhost\runner02\home\github-runner\.cache\desktop-linux\vbox-proof\bench\runs\<run-id>\serial.log
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

1. wait for the GRUB serial hotkey prompt;
2. press `t`, enter the selected boot entry editor and append
   `console=ttyS0,115200 textmode=1`;
3. press Ctrl+X;
4. require the installer kernel/Hardware-detection serial milestone or fail the
   run.

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
- powered-off GPT/LUKS/ESP read-back.

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

Credential values are stored only in the local proof cache and are never
committed to git. Before a run, the OEMDRV builder renders a runtime
`autoinst.xml` from the source-controlled template:

- a present recovery passphrase is written into the runtime LUKS `crypt_key`
  and its AutoYaST question is removed;
- a present root password is written into the runtime root-user profile and its
  AutoYaST question is removed;
- a present TPM PIN is carried as a local OEMDRV file and the pre-script loads
  it into the stock `sdbootutil-tpm2-pin` keyring entry; its question is
  removed;
- any missing value keeps its normal AutoYaST password question.

The harness never types credential values through VirtualBox keyboard
injection. Keyboard control is limited to deterministic installer/GRUB
navigation.

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
  YaST startup and `VMBENCH_PROFILE_READY` within the timeout;
- when all three local proof credentials exist, no credential prompt is
  expected;
- when one or more values are absent, only those missing values remain as
  ordinary AutoYaST password prompts.

FAIL:

- any required serial milestone is absent within its timeout;
- the runtime profile exposes a prompt for a credential that was present in the
  local credential source;
- the harness attempts to type a credential value itself.

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
2. build the local OEMDRV, embedding every credential present in the host-side
   credential file and retaining AutoYaST prompts only for missing values;
3. boot via Gate-0 serial method;
4. if any credential is missing, enter only that missing value through the
   normal AutoYaST UI; the harness remains passive;
5. require visible serial milestones through storage proposal, package install,
   target configuration and bootloader installation;
6. stop the first installer reboot before the attached installer media can
   start AutoYaST a second time.

PASS requires all of:

- guard VDI unchanged;
- target VDI changed;
- GPT has an ESP plus one outer encrypted payload partition;
- the outer payload is LUKS2 with the owner recovery-passphrase keyslot;
- the same outer LUKS2 device has the TPM2 token with PIN/PCR-lock metadata;
- the unlocked payload contains LVM VG `system`;
- VG `system` contains root, home and swap LVs;
- root is Btrfs and home is the persistent-state LV;
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
- exactly one interactive TPM2 PIN entry unlocks the outer LUKS2 container;
- root, home and swap LVs require no additional cryptographic credential;
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

- the target has exactly one non-ESP LUKS2 payload container;
- `pvs`, `vgs` and `lvs` show VG `system` inside that unlocked container;
- root, home and swap LVs exist with the expected roles;
- `findmnt /` reports Btrfs;
- Snapper root configuration and snapshots exist;
- `/home` is on its persistent LV and is outside normal root rollback;
- swap is the VG swap LV and is not a second LUKS device.

## Gate 5 — boot trust and portability

Verify separately:

- Secure Boot on;
- normal TPM2+PIN unlock of the single outer LUKS2 container with one PIN;
- owner-passphrase recovery unlock of the same container with one passphrase;
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
2. update `VM_PROOF.md` with the accepted live result;
3. read back against Product First and Economy First;
4. commit;
5. synchronize to GitHub;
6. add an issue #1 checkpoint for a materially new gate result.

No next gate begins while the current gate has an unexplained failure.