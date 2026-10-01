# Portable workstation — business requirements

## Authority

This document defines the **authoritative business requirements** for the portable workstation.

For every numbered item below:

- **Requirement** is authoritative.
- **Example** is non-authoritative and illustrative only.
- An example may be replaced, removed, or implemented differently without changing the requirement.
- A technical mechanism mentioned in an example does **not** become an architectural requirement merely because it appears here.

Technical architecture and implementation choices in other files must serve these requirements. They may change when a simpler, cheaper, better-supported, or otherwise superior implementation satisfies the same authoritative requirements.

## Requirements

### 1. Portable working environment

**Requirement:** The complete working environment and the persistent state needed to continue work must move with the removable device.

**Example:** The operating system, user files, browser profile, and application state live on an external SSD rather than on the computer's internal disk.

### 2. Portability must not depend on the original host

**Requirement:** After moving the removable device to another compatible machine, the owner must retain access to their data and the ability to use the working environment without depending on unique state or resources of the previous computer.

**Example:** If normal unlock uses a machine-specific hardware trust mechanism, the product also provides an owner-authorized recovery path that works on another compatible machine.

### 3. No mandatory additional capital investment

**Requirement:** The solution must be implementable using an already available compatible computer and removable device, without requiring purchase of additional specialized infrastructure or hardware.

**Example:** No dedicated HSM, enterprise key-management server, or second hardware token is required.

### 4. Minimal operational and engineering burden

**Requirement:** The workstation must be an operational product, not a separate software project that requires ongoing custom engineering to remain usable.

**Example:** A supported product capability is preferred over maintaining a custom bootloader, custom PKI, bespoke installer framework, or equivalent owner-maintained mechanism.

### 5. Do not weaken relevant platform security

**Requirement:** Using the portable workstation must not require weakening or bypassing security protections that materially contribute to the required security of the workload unless the solution replaces them with an equal or stronger supported protection.

**Example:** A solution may use UEFI Secure Boot, another vendor-supported verified-execution mechanism, or a different architecture entirely, but it must not gain compatibility merely by removing a protection that the workload still relies on.

### 6. Detect unauthorized pre-unlock modification

**Requirement:** Modification of executable or configuration state that can influence execution before protected persistent data is unlocked must not allow an attacker to silently obtain owner secrets or run a modified system as trusted.

**Example:** Replacing a bootloader, kernel, or early-boot image on a stolen device results in verification failure rather than a convincing counterfeit unlock prompt.

### 7. Confidentiality if the removable device is lost

**Requirement:** Loss or theft of the removable device alone must not provide access to user data or persistent workstation state.

**Example:** Persistent data is encrypted and requires owner authorization to unlock.

### 8. Independence from host persistent storage

**Requirement:** The portable workstation must not use the host computer's internal persistent storage as part of its own required working state.

**Example:** User profiles, swap, boot artifacts, and application data are not stored on the ASUS internal SSD.

### 9. No persistent disruption of the host

**Requirement:** After the portable device is removed, the host computer must continue its normal operating and boot behavior without repair or restoration work.

**Example:** The portable system does not replace the host OS bootloader or permanently change the host boot order.

### 10. Explicit user choice to enter the portable environment

**Requirement:** Entering the portable working environment must be an explicit user action rather than a permanent change to the host computer's normal behavior.

**Example:** The user selects the removable device from a one-time firmware boot menu.

### 11. Reproducible initial provisioning

**Requirement:** There must be a supported, repeatable process that turns a selected removable device into a complete ready-to-use workstation with minimal manual work.

**Example:** A supported installer, image deployment, appliance provisioning flow, or equivalent product mechanism creates the ready working environment.

### 12. Protect against destruction of the wrong device

**Requirement:** Destructive provisioning operations must run only after the intended target device has been identified unambiguously.

**Example:** Provisioning binds to a stable identifier of the selected external SSD rather than choosing the first USB disk.

### 13. Replace system state without loss of required persistent state

**Requirement:** There must be a supported recovery or replacement operation that can replace the workstation's system state with a known-good state while preserving the user and application state that is intended to survive system replacement.

**Example:** The implementation may use reinstall, image redeployment, reset, rebase, rollback to a clean deployment, or another supported mechanism while preserving required persistent workload state.

### 14. System replacement need not preserve the previous system instance

**Requirement:** Preserving required persistent state during system replacement does not require preserving the previous system instance or providing a return path to that specific instance.

**Example:** A previous installation, deployment, image, or system instance may be discarded completely once the required persistent state is safely preserved.

### 15. Independent lifecycles for system state and persistent user/application state

**Requirement:** Replacing or restoring system state must not automatically roll persistent user data and persistent application state back to an older point in time.

**Example:** Rolling back the OS does not roll back documents or a browser profile.

### 16. Safe rollback point before managed system updates

**Requirement:** Before changing managed system state through an update, a usable recovery point for the previous working system state must exist.

**Example:** The implementation may use a filesystem snapshot, an A/B image, or another rollback mechanism.

### 17. Fast recovery from a failed system update

**Requirement:** A failed system update must not require a complete manual reinstall and backup restoration when a previously working system state remains available.

**Example:** The workstation can return to a previous snapshot or previous bootable image.

### 18. Security-maintenance acceptance before sensitive work

**Requirement:** Sensitive workload must not begin while the workstation is in a system state that is disallowed by the current maintenance and security policy.

**Example:** Depending on the selected product, compliance may be established by a pre-session maintenance gate, booting an already updated atomic deployment, validating an immutable image, or another supported mechanism that demonstrates the running state is acceptable.

### 19. Unified maintenance policy for managed executable software

**Requirement:** Managed executable software should, where practical, follow one coherent maintenance policy so that independent unmanaged patch lifecycles do not accumulate.

**Example:** The OS, browser, and normally managed applications are updated during the same required maintenance cycle.

### 20. Owner-operated recovery without unavailable external dependency

**Requirement:** The owner must have a practical way to recover access to the workstation and its data after failure of the normal boot path or after moving to another compatible computer, without depending on an unavailable external organization or infrastructure service.

**Example:** Recovery can use official installation/recovery media together with an owner-held recovery credential.

### 21. Fail safely instead of guessing

**Requirement:** When an operation cannot reliably establish the conditions required for data safety or the claimed security level, it must stop rather than make potentially destructive assumptions.

**Example:** If an installer cannot identify the intended external disk unambiguously, it stops instead of choosing the most likely candidate.

### 22. Supported product outcome over internal technical form

**Requirement:** Technical architecture must be selected for its ability to satisfy these business requirements with minimal cost, complexity, and maintenance burden; particular internal mechanisms are not goals in themselves.

**Example:** If a supported product satisfies portability, confidentiality, execution integrity, system replacement, and recovery requirements without a previously proposed operating system, filesystem, boot format, storage topology, or deployment model, the supported product is preferred and the technical architecture may be changed.

### 23. Workload fitness

**Requirement:** The portable workstation must reliably support a limited set of browser-centric operations involving sensitive secrets and potentially irreversible high-value actions. System selection must consider only capabilities required for this workload; the presence or absence of unrelated general-purpose desktop functionality is not itself a selection criterion.

**Example:** A modern browser, required browser extensions, and necessary local integrations are material. The presence of an office suite, PDF reader, media player, or other unused applications is neither an advantage nor a disadvantage unless it affects security, maintenance burden, or execution of the target workload.

### 24. Minimal routine administration

**Requirement:** Keeping the portable workstation secure and operational must not require regular manual system administration beyond actions that are genuinely necessary for normal use.

**Example:** In the normal working path, the user should not need to manually maintain boot artifacts, package state, snapshots, keys, recovery state, or routine system updates.

### 25. External owner-controlled hardware integration

**Requirement:** The portable workstation must support the external owner-controlled hardware devices required by the target workload through a practical, supported interaction path.

**Example:** A required USB or HID authorization device can be connected and used from the workload environment without unsupported drivers, custom device forwarding infrastructure, or routine host-specific reconfiguration.
