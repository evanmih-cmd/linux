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

**Example:** A supported Ubuntu feature is preferred over maintaining a custom bootloader, custom PKI, or bespoke installer framework.

### 5. Preserve platform trusted-boot protection

**Requirement:** Using the portable workstation must not require disabling the platform's normal trusted-boot protection.

**Example:** UEFI Secure Boot remains enabled.

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

**Example:** A supported unattended installation profile creates a ready Ubuntu desktop environment.

### 12. Protect against destruction of the wrong device

**Requirement:** Destructive provisioning operations must run only after the intended target device has been identified unambiguously.

**Example:** Provisioning binds to a stable identifier of the selected external SSD rather than choosing the first USB disk.

### 13. Reinstall without loss of persistent state

**Requirement:** There must be a reinstall operation that replaces the system portion of the workstation while preserving user data and persistent application state that is intended to survive reinstall.

**Example:** The OS is replaced while documents, browser profile, and persistent application data remain intact.

### 14. Reinstall need not preserve the previous OS installation

**Requirement:** Preserving persistent state during reinstall does not require preserving the previous system installation or providing a rollback path to that specific installation.

**Example:** The old system root may be destroyed and recreated if the required persistent state is preserved.

### 15. Independent lifecycles for system state and persistent user/application state

**Requirement:** Replacing or restoring system state must not automatically roll persistent user data and persistent application state back to an older point in time.

**Example:** Rolling back the OS does not roll back documents or a browser profile.

### 16. Safe rollback point before managed system updates

**Requirement:** Before changing managed system state through an update, a usable recovery point for the previous working system state must exist.

**Example:** The implementation may use a filesystem snapshot, an A/B image, or another rollback mechanism.

### 17. Fast recovery from a failed system update

**Requirement:** A failed system update must not require a complete manual reinstall and backup restoration when a previously working system state remains available.

**Example:** The workstation can return to a previous snapshot or previous bootable image.

### 18. Required maintenance before normal work

**Requirement:** In the normal usage path, the user must not begin an ordinary working session until required system maintenance and validation policies have completed successfully.

**Example:** Required updates and health checks complete before the graphical login is released.

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

**Example:** If a supported Ubuntu mechanism satisfies portability, confidentiality, trusted boot, reinstall, and recovery requirements without a previously proposed filesystem, boot format, or storage topology, the supported mechanism is preferred and the technical architecture may be changed.
