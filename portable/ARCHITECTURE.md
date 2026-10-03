# Portable workstation — architecture

## Status and authority

This document defines the selected technical architecture for the portable
workstation.

The authoritative requirements are in
[`BUSINESS_REQUIREMENTS.md`](BUSINESS_REQUIREMENTS.md). Requirements win over
this document.

**Product selection is complete: openSUSE Tumbleweed is selected.** Remaining
work is implementation/proof. Reopen product selection only if a residual gate
cannot be satisfied with supported openSUSE mechanisms and the only workaround
would be owner-maintained security-sensitive infrastructure.

The architecture follows two ordering rules:

- **Product First:** exhaust supported production mechanisms before owner-built
  substitutes.
- **Economy First:** among requirement-satisfying outcomes, minimize total
  lifecycle cost: implementation, routine administration, update/recovery
  burden, debugging, capital cost and expected loss from failure. For the target
  workload, a path that can silently capture an owner secret is vastly more
  expensive than a fail-closed path that occasionally requires recovery.

RC/preview/test-only product paths are excluded. An upstream “experimental”
interface label is not automatically a security failure; the concrete failure
mode, distro integration and recurring ownership cost are evaluated instead.

## Hardware and workload baseline

Primary host:

- ASUS TUF A14 FA401EA;
- AMD Ryzen AI Max+ 392;
- Radeon 8060S / gfx1151;
- 64 GB RAM;
- removable SSD containing the workstation;
- host Windows/internal storage outside workstation authority.

Target workload:

- Google Chrome with the required wallet/browser extensions;
- browser-centric sensitive operations and irreversible high-value actions;
- Ledger hardware wallet through the supported Chrome/WebHID/udev path;
- no requirement to optimize for unrelated desktop applications.

## Product-selection conclusion

The realistic first-class workload universe was reduced to Windows, macOS and
the Linux families for which Google publishes supported Chrome desktop packages:
Ubuntu/Debian, openSUSE and Fedora. Ledger support was checked separately.

Tumbleweed wins because it is the lowest-cost GA path found that combines:

- Chrome/Ledger workload fitness;
- Secure Boot plus an authenticated early-boot path;
- TPM2+PIN plus an independent owner recovery credential;
- offline installation;
- exact-target declarative provisioning;
- portable/no-variable boot support;
- independent system and persistent-data lifecycles;
- bootable system rollback;
- current AMD support.

Closest competitor Ubuntu 26.04.1 has a strong Canonical-managed UKI TPM-FDE
stack and credible snap/APT rollback. It loses because no supported GA stock
TPM-FDE path was found that replaces the system layer while preserving a
separately managed persistent browser/user/application state. Building that
separation around Canonical's hybrid FDE would transfer integration ownership
back to this project.

Debian and Fedora remain technically capable but require more owner/cross-project
UKI/FDE integration. Leap 16.1 and Aeon are not GA at this checkpoint; Leap 16.0
does not expose the complete current Tumbleweed path. Slowroll intentionally
delays changes relative to Tumbleweed and is not preferred for this
security-sensitive workload. Windows has no current supported Windows-To-Go
replacement; macOS is not a supported ASUS product; ChromeOS Flex, Qubes and
other families fail other hard gates recorded in issue #1.

## Trust and boot model

### Normal primary-host path

Target path:

```text
UEFI firmware
    ↓
Secure Boot
    ↓
shim / stock openSUSE boot chain
    ↓
official vendor-signed UKI path
    ↓
authenticated embedded early userspace
    ↓
TPM policy + short owner TPM2 PIN
    ↓
outer LUKS2 unlock
    ↓
system + persistent volumes
```

The exact shim/systemd-boot/UKI handoff is an implementation proof gate. The
critical invariant is that the code which renders the normal secret prompt is
authenticated before the user types the TPM PIN. A modified ESP, BLS entry,
kernel command line or other pre-unlock state must not be able to present a
convincing secret-stealing prompt and continue as trusted.

The official Tumbleweed `uki-default` is the selected UKI candidate. Current
Factory packaging signs it with an openSUSE Secure Boot signing certificate
which is not in the generic stock host trust chain; the primary host therefore
enrolls that **public vendor signing certificate** through MOK.

Accepted MOK scope:

- one-time primary-host trust enrollment is acceptable;
- the project does not generate or retain a private signing key;
- the project does not re-sign every kernel/UKI;
- recurring MOK enrollment after normal updates is not acceptable;
- the exact certificate scope and revocation/update behavior remain proof items.

### TPM policy

Tumbleweed/openSUSE currently integrates `sdbootutil` and
`systemd-pcrlock`/NVIndex for TPM-bound FDE.

Upstream still describes parts of the pcrlock interface as experimental.
openSUSE nevertheless deliberately moved to this mechanism to avoid the
rollback weakness of the older signed-PCR-policy design. Treat the remaining
risk as interface/lifecycle maturity that must be tested across updates, not as
evidence that the cryptographic property is weaker.

### Credential model

Normal and recovery credentials are distinct by design.

**Normal boot credential**

- short TPM2 PIN, e.g. a human-usable numeric PIN;
- protected by the TPM-bound authorization path;
- entered on every normal boot.

**Recovery credential**

- separate strong LUKS passphrase;
- sized for resistance to offline guessing if the SSD is stolen;
- stored/remembered by the owner independently of the machine;
- usable when the original TPM or host is unavailable.

The short TPM PIN must never become the only independent LUKS recovery
credential.

Current `sdbootutil` supports a dedicated TPM PIN source:
`%user:sdbootutil-tpm2-pin`. If the selected YaST/Offline Image still maps the
storage password to the legacy generic secret, AutoYaST may ask for the TPM PIN
separately and place it only in that short-lived installer keyring entry. This
is accepted as a small installer-only integration delta; no clear-text PIN is
embedded in installation media or persisted as configuration.

### Emergency/new-host recovery

```text
trusted official owner-controlled recovery/install media
    ↓
owner enters strong LUKS recovery passphrase
    ↓
persistent state becomes accessible
    ↓
repair if cheap, otherwise replace system/root
    ↓
establish fresh host-specific MOK/TPM state
```

Recovery is intentionally exceptional. In-place repair of the previous TPM
relationship is not a requirement; clean system replacement is acceptable.

## Removable boot and host isolation

Required invariants:

- all required workstation state is on the removable SSD;
- the internal ASUS disk and ESP are never targets;
- the user enters through a one-time firmware boot choice;
- the external ESP contains the standard removable fallback path;
- no persistent UEFI boot entry is required;
- provisioning/runtime use the supported no-variable/no-NVRAM behavior;
- `BootOrder` and `BootNext` are not used to make the workstation sticky;
- with the SSD removed, the host resumes normal Windows boot with no repair.

Current `sdbootutil` exposes `--portable` and `--no-variables`; the final
proof must show that the selected installer path actually produces the required
fallback artifacts and leaves NVRAM unchanged.

## Storage and state model

Selected topology:

```text
removable SSD
├── GPT
├── EFI System Partition
└── LUKS2
    └── LVM PV / VG
        ├── root LV  → Btrfs system root + Snapper
        ├── home LV  → persistent user/browser/application state
        └── swap LV  → real disk-backed swap
```

Why LVM is present:

- Btrfs itself is not a requirement.
- Requirements 13 and 15 require a destructive system replacement to have a
  clear boundary that preserves current user/application state.
- A separate root LV and persistent LV make that boundary declarative and easy
  to prove.
- The swap LV is inside the already-unlocked LUKS boundary, so it does not
  require a second boot secret or second TPM enrollment.

Hibernation is disabled. Swap is for normal memory pressure only.

Root uses Btrfs/Snapper because it is the cheapest native openSUSE mechanism for
a usable pre-update rollback point and bootable recovery. Persistent state is
not part of root rollback.

Normal persistent state belongs on the preserved `/home` LV unless a specific
application proves it needs another preserved path. Do not create a custom
persistence framework without such evidence.

## Provisioning

### Selected production direction

Use the official Tumbleweed **Offline Image** plus **AutoYaST**.

The final media must:

- install with networking disabled;
- carry its unattended profile and all baseline packages locally;
- identify the removable SSD by a stable persistent identity and fail if it is
  absent;
- leave the internal disk/ESP untouched;
- preserve Secure Boot;
- create the final LUKS2 → LVM topology;
- install the strong recovery passphrase without exposing it in the media;
- obtain the short TPM PIN interactively or through an equally safe supported
  secret channel;
- leave host NVRAM/boot order unchanged;
- create the removable fallback EFI path;
- be reproducibly built from a verified official image.

### Accepted installer-only deltas

Two current product-integration gaps are allowed only as small,
installer-scoped deltas and should be deleted when upstream no longer needs
them:

1. **No-NVRAM AutoYaST import.** If the exact Offline Image still has the
   YaST serialization omission where systemd-boot/BLS runtime supports
   `update_nvram` but AutoYaST does not import it, use the smallest YaST
   installer overlay/driver update that imports the existing product property.
   Do not fork the installed bootloader.
2. **Separate TPM PIN delivery.** If YaST still feeds the LUKS password through
   the legacy generic `sdbootutil` secret, use an AutoYaST ask/script hook to
   put the separately entered short PIN only in
   `%user:sdbootutil-tpm2-pin`. The installed system receives TPM enrollment,
   not a clear-text PIN file.

These deltas are acceptable only because they adapt installer plumbing to
existing supported product capabilities. They must not implement cryptography,
boot verification, package management or TPM policy themselves.

Agama development/test media are not a production path because baseline
installation must be offline and GA.

## System replacement and rollback

### Normal failed-update recovery

Use openSUSE's supported system rollback mechanisms. Root rollback must not roll
back the persistent `/home` LV.

A usable recovery point must exist before managed system changes. A previous
known-good root must be bootable/recoverable without first making the broken
userspace fully operational.

### Clean system replacement

Reinstall is a first-class hard fallback, not an exceptional data-migration
project.

The reinstall profile must:

1. identify the same removable SSD fail-closed;
2. unlock the existing outer LUKS2 with the strong owner recovery credential;
3. preserve the persistent LV and its filesystem;
4. destroy/recreate or reformat only replaceable system/root state;
5. recreate swap if desired;
6. install a known-good Tumbleweed system;
7. recreate boot artifacts on the external ESP;
8. establish fresh host-specific TPM/MOK state when required.

The old system instance need not survive.

AutoYaST/LVM preservation controls such as reusing existing volumes and
`keep_unknown_lv`/equivalent current product semantics must be proven against
the exact selected packages before this gate passes.

## Maintenance policy

The requirement is the outcome, not a particular updater.

Before sensitive work:

- managed system state must be current under the selected policy;
- a usable previous-system recovery point must exist;
- update failure keeps recovery/admin access but blocks sensitive work;
- after successful update, stale executable mappings must not survive into the
  sensitive session;
- the user receives an explicit current/success/failure result.

Prefer the native Tumbleweed update stack. Current candidates are the distro
`os-update`/`zypper dup` path with native Snapper integration or
`transactional-update` if it materially lowers failure cost. Select between
them by proof of requirements 16–19, not by preserving a previous design.

Do not implement a package manager, snapshot engine or boot manager in project
code. Project-owned maintenance code may only orchestrate product mechanisms
and gate the sensitive workload.

kexec is not accepted as equivalent to a fresh Secure Boot/measured-boot path
for transitions that require a platform reboot.

## Browser and Ledger

Use vendor Google Chrome, because Chrome support is part of the workload gate.
Baseline offline media must include the Chrome RPM and required local
dependencies/udev configuration. Once networking is available, Chrome should
remain inside the same mandatory maintenance session even if its RPM repository
is vendor-owned rather than openSUSE-owned.

Ledger uses the supported Chrome/WebHID path and vendor-published Linux udev
rules. Avoid VM forwarding or custom USB middleware.

## Validation gates

### Residual go/no-go gates before implementation is accepted

1. Prove that the official vendor-signed UKI path is the code path that renders
   the normal TPM-PIN prompt and that mutable external early-boot state cannot
   steal the PIN while appearing trusted.
2. Prove normal UKI/kernel/PCR-policy updates require neither owner signing nor
   recurring MOK enrollment.
3. Prove root snapshot rollback remains bootable and compatible with the
   authenticated UKI/PCR lifecycle.
4. Prove AutoYaST fresh install and reinstall: exact target, final LUKS2→LVM
   topology, separate short TPM PIN + strong recovery passphrase, root
   replacement and persistent-LV preservation.
5. Repeat offline installation, internal-disk sentinel preservation, removable
   fallback and unchanged NVRAM on the final topology.
6. Validate the ASUS FA401EA hardware path and real Chrome + Ledger workload.

If any gate can be closed only with owner-maintained security-sensitive boot
code, private signing infrastructure or a custom FDE implementation, stop and
reopen product selection.

## Accepted compromises

The selected product consciously accepts:

- one-time primary-host MOK enrollment of an openSUSE vendor public signing
  certificate;
- upstream pcrlock interface-maturity risk because openSUSE owns the integrated
  lifecycle and the mechanism improves rollback resistance;
- higher update volume from a rolling distribution, offset by native rollback;
- two owner credentials with different purposes: a short TPM PIN and a strong
  recovery passphrase;
- possible manual one-time boot-menu selection after a full firmware reboot.

These are narrower and cheaper than owner-managed PKI, bespoke boot code,
enterprise key infrastructure or custom FDE/update engines.
