# Windows security workstation — business requirements

## Authority

This document defines the **authoritative business requirements** for the Windows security workstation.

For every numbered item below:

- **Requirement** is authoritative.
- **Example** is non-authoritative and illustrative only.
- A technical mechanism mentioned in an example does **not** become an architectural requirement merely because it appears here.
- Architecture and implementation may change when a simpler, cheaper, better-supported solution satisfies the same requirement.

The previous portable-Linux requirements remain preserved under `portable/`, but they are no longer the product requirements for this workstation.

## Requirements

### 1. Fixed primary workstation is acceptable

**Requirement:** The production environment may be bound to the primary ASUS workstation. Moving the complete operating environment between arbitrary compatible computers is no longer required.

**Example:** Hardware-bound identity, encryption, and recovery mechanisms may use the ASUS TPM/Pluton and firmware.

### 2. Existing host installation must remain recoverable

**Requirement:** Building the Windows security workstation must not destroy the existing Windows installation or make it dependent on the new installation.

**Example:** Windows 11 Pro is installed to the second SSD with its own boot/recovery structures while the existing Home installation remains independently recoverable.

### 3. Security endpoint over local-compute portability

**Requirement:** The workstation is primarily a trusted user-identity and credential endpoint for cloud and high-value services, not a portable store of all working data.

**Example:** Cloud data may remain in cloud services while the local machine protects identity keys, session authorization, recovery material, and secure interaction with external hardware.

### 4. Compromise containment across trust domains

**Requirement:** Compromise of one software trust domain must not automatically expose long-lived secrets held by stronger independent trust domains.

**Example:** Compromise of an ordinary browser, user session, SYSTEM, or the normal OS kernel should not by itself imply extraction of secrets protected by hardware-backed or VBS-isolated mechanisms.

### 5. Minimize trust in the ordinary OS

**Requirement:** Security-critical secrets should, where supported, be protected by mechanisms whose confidentiality does not depend solely on the integrity of the ordinary Windows kernel.

**Example:** Device-bound keys may be protected by TPM/Pluton and application secrets may be isolated through VBS-backed mechanisms.

### 6. Verified and measured boot state

**Requirement:** The workstation must not silently run modified early-boot code as trusted normal state.

**Example:** Secure Boot, measured boot, BitLocker PCR policy, and supported launch protections cause unauthorized boot-path changes to fail closed or require explicit recovery.

### 7. Confidentiality at rest

**Requirement:** Theft or loss of either workstation SSD alone must not disclose protected workstation data.

**Example:** Each Windows OS volume is protected by BitLocker and does not rely on another OS volume being unlocked.

### 8. Independent OS-volume trust

**Requirement:** Booting one installed Windows environment must not automatically grant plaintext access to another protected OS volume.

**Example:** OS-volume auto-unlock is not configured between the Home and Pro installations.

### 9. Strong normal preboot authorization

**Requirement:** Normal access to the production OS must require owner authorization before the protected OS volume is released.

**Example:** BitLocker uses TPM plus startup PIN for normal boot and an offline recovery key for exceptional recovery.

### 10. Separate preboot and in-OS authentication roles

**Requirement:** A credential intended for preboot disk release should not become the routine userspace authentication secret when a stronger supported in-OS identity mechanism is available.

**Example:** BitLocker startup PIN is used only preboot; Windows Hello/ESS Face is used for normal in-OS user verification, with a distinct Hello PIN as fallback.

### 11. Hardware-backed user verification

**Requirement:** Normal in-OS authorization for sensitive operations should use a hardware-backed user-verification path that resists software-only impersonation.

**Example:** Built-in IR camera + Windows Hello Enhanced Sign-in Security is preferred over a reusable password prompt.

### 12. Protect credential collections from bulk theft

**Requirement:** A single compromised application or ordinary OS context must not have an unrestricted bulk-export path for the user's protected credential collection.

**Example:** A credential broker exposes narrow per-record release operations instead of exporting the vault master key or whole plaintext database.

### 13. Presence is not the same as transaction context

**Requirement:** The design must distinguish proof that the user is present from proof that the user knowingly authorized a specific sensitive action.

**Example:** Windows Hello may prove user presence, while a future trusted-display mechanism can bind confirmation to the exact credential or transaction being released.

### 14. Trusted-context hardening may be phased

**Requirement:** Lack of a generic trusted display for arbitrary third-party operations is not a blocker for version 1 if the residual confused-deputy risk is explicit and long-lived secret extraction remains prevented.

**Example:** Version 1 may use ESS/Hello plus a narrow VBS credential API; an external authenticated display/button can be researched later.

### 15. External hardware must remain an independent trust domain

**Requirement:** Required external authorization devices must retain their own security boundary rather than importing their private keys into Windows.

**Example:** Ledger keeps crypto private keys on-device and requires transaction verification on its own display.

### 16. Independent recovery path

**Requirement:** Failure or replacement of the ASUS TPM/platform must not irreversibly destroy access to protected user credentials.

**Example:** An offline recovery secret or separate hardware token can recover the credential vault after reinstall or hardware replacement.

### 17. System state is disposable

**Requirement:** The Windows installation must be replaceable with a known-good supported installation without treating the current OS instance as irreplaceable state.

**Example:** A compromised or broken installation can be wiped and rebuilt from official Microsoft media, then cloud/app state is restored through defined recovery mechanisms.

### 18. Recovery must not depend on a healthy current OS

**Requirement:** The owner must retain a practical recovery path when the installed OS no longer boots or is no longer trusted.

**Example:** Official Microsoft installation/recovery media plus offline BitLocker and credential-recovery material are sufficient to begin recovery.

### 19. Network independence applies to recovery start, not full provisioning

**Requirement:** Initial recovery must be able to start from trusted local media without relying on the compromised OS, but the finished Windows workstation may use the network for supported updates, drivers, activation, and application installation.

**Example:** The official ISO boots and installs the OS offline; supported vendor software and updates may be fetched after the new OS is running.

### 20. Security maintenance before sensitive work

**Requirement:** Sensitive high-value work must not proceed while the workstation is knowingly outside its required maintenance/security state.

**Example:** Required Windows security updates and security-platform state are checked before sensitive browser or crypto work.

### 21. Coherent supported maintenance

**Requirement:** Managed executable software should use supported vendor maintenance channels and avoid independent custom patch mechanisms where practical.

**Example:** Windows uses Windows Update, Chrome uses the official Google channel, and hardware/security components use supported Windows/OEM update paths.

### 22. Minimal routine administration

**Requirement:** Normal secure use must not require recurring manual maintenance of low-level boot artifacts, keys, policy internals, or bespoke security plumbing.

**Example:** Supported BitLocker, Windows Hello, VBS, Defender, and platform policies are preferred over owner-maintained cryptographic frameworks.

### 23. Reproducible provisioning and audit

**Requirement:** The desired workstation configuration must be expressible and checkable repeatably rather than depending on remembered manual setup.

**Example:** A VM bench develops unattended installation/configuration plus a machine-readable PASS/FAIL audit reused on the physical ASUS.

### 24. VM proof and hardware proof must not be conflated

**Requirement:** Virtual-machine testing may prove software configuration and automation, but hardware-specific security claims require validation on the actual target hardware.

**Example:** A VM can prove unattended setup and audit logic; ESS camera isolation, Pluton, DRTM, physical SSD isolation, and real Ledger USB behavior remain bare-metal gates.

### 25. Fail safely instead of guessing

**Requirement:** Destructive, security-critical, or recovery operations must stop when the required target or security condition cannot be established reliably.

**Example:** The owner manually identifies the dedicated RAID virtual disk in interactive WinPE DiskPart; SSD1 is taken Offline before destructive partitioning. The XML must not silently wipe a hardcoded DiskID before the owner confirms the target. The disk choice is an intentionally interactive exception to unattended provisioning.

### 26. Official-source software baseline

**Requirement:** Operating-system and security-critical executable software must come from authoritative vendor sources with integrity/provenance verification where available.

**Example:** Windows ISO comes from Microsoft and its SHA-256 is matched against Microsoft; Chrome comes from Google; no reseller ISO or activation tool is trusted.

### 27. Workload fitness

**Requirement:** The workstation must reliably support the browser-centric, credential, and crypto workflows that motivate the product; unrelated desktop features are secondary.

**Example:** Chrome, required wallet extensions, Windows Hello, Ledger integration, and recovery matter more than minimizing the installed application count.

### 28. Supported product outcome over internal mechanism

**Requirement:** Product security, usability, recovery, cost, and maintenance burden take priority over any previously selected technical mechanism.

**Example:** If a standard Windows mechanism satisfies a requirement better than custom code, use the Windows mechanism even if an earlier design proposed something else.

### 29. Immediate TPM-backed BitLocker; owner-controlled startup PIN

**Requirement:** Encryption without active key protection is not sufficient. Provisioning must activate TPM and independent recovery protectors promptly. The owner selects the startup PIN separately after installation. The final gate requires TPM+PIN and removal of any TPM-only normal-boot bypass.

**Example:** Configure TPM and recovery password protectors, require ProtectionStatus On, and confirm that the owner has recorded the 48-digit recovery password offline before PIN enrollment. No real PIN or recovery secret in media, repository, logs or diagnostics.

### 30. Mandatory Administrator Protection

**Requirement:** The Windows 11 Administrator Protection mode is mandatory, not an optional hardening. It must be operational, not merely present in desired-state configuration.

**Example:** Set TypeOfAdminApprovalMode=2, reboot and confirm Hello-based authorization where supported, including physical ASUS confirmation.

### 31. Firmware-locked production VBS and HVCI

**Requirement:** After actual hardware runtime and recoverability are validated, production VBS/HVCI must use UEFI Lock to prevent remote/policy-only disable. The owner can physically access ASUS firmware. Fail-stop boot is not required.

**Example:** Apply the physical ASUS-only DSC lock overlay after validating live VBS/HVCI and WinRE, then verify effective locked state after reboot. Do not set Mandatory=1 or UEFI lock in the NEM-backed test VM.

### 32. Windows Sandbox profiles with narrow host access

**Requirement:** Offer separate default offline file-triage and network-observation Sandbox modes, with no writable host folder, credentials, device redirection or shared clipboard.

**Example:** Windows Pro optional feature, two reviewed WSB files, one dedicated read-only input folder, Protected Client, restricted vGPU, audio/video and printer redirection.

### 33. Internet-only networking for the observational sandbox

**Requirement:** The networked Sandbox may reach public internet services but may not access the ASUS host, local LAN, non-public/link-local/IPv6-local endpoints or VPN networks. Unfiltered default-switch access is not an accepted implementation.

**Example:** Verify Sandbox-specific host-side Hyper-V firewall or a separate filtered VM network gateway with denied IPv4/IPv6 private/host/VPN routes, working public HTTPS and DNS, and persistent rules after restarting Sandbox.

### 34. Convenient observability and control of suspicious connections

**Requirement:** For behavioral analysis, the user should be able to inspect process identity, attempted destination, block/allow outcome and connection history. Informational guest monitoring is not the same as host-enforced blocking or durable evidence.

**Example:** Resource Monitor for initial per-process TCP observation; a separately isolated and enforced firewall/monitor for actual deny or prompt decisions. No trusted security guarantee can rely solely on malware-controllable software inside the guest.

### 35. Browsing trust-domain separation and official crypto tools

**Requirement:** Everyday browsing and dedicated sensitive/crypto workloads must use separate browsers. All wallet and security software must come through vetted publisher channels. Never provision real wallet secrets as part of the workstation image.

**Example:** Microsoft Edge for normal use, Chrome for sensitive browsing with exactly the six publisher-verified wallet extensions, official KeePass and Ledger Wallet, and hardware signing/Hello checks on ASUS.

### 36. Installation readiness is a distinct, fail-closed release gate

**Requirement:** The owner prepares the bootable USB using the official Microsoft Windows ISO and explicitly selects the Windows target RAID virtual disk in the supported interactive WinPE DiskPart interface. The project does not create USB media, hard-bind SSD2 by NVMe serial, or infer target choice from a disk index. SSD1 must be Offline in WinPE. The first live two-disk Windows Setup attempt proved that SSD1 Offline plus choosing a blank RAID LUN does NOT guarantee a target-local ESP: Setup created only MSR and NTFS and failed boot-file servicing. Therefore this procedure is rejected. The supported installation design must explicitly guarantee target-local ESP/BCD and recovery on the manually selected LUN using documented Microsoft tools, while never modifying the existing SSD1; exact predeclared MiB partition sizes are not a goal by themselves. Boot OS choice must be by selecting the actual boot disk / RAID LUN in the ASUS firmware boot-device menu, NOT by choosing between Windows Boot Manager menu items or two firmware NVRAM Windows Boot Manager entries. The firmware must expose both devices and each must boot independently; prove RAID LUN firmware support on hardware rather than assuming it. When the RAID LUN is enlarged later, the supported rare maintenance sequence is to disable and back up WinRE, delete only its verified partition, extend C: while reserving WinRE space, recreate an appropriately sized WinRE partition after C: and verify boot, recovery and BitLocker; no automatic partition-moving manager is required. The RAID allocation layer is an accepted architecture; proof of RAIDXpert2 hardware feasibility is a separate experiment outside this implementation issue. Installation approval still requires a tested mixed-mode interaction, a reproducible configuration/recovery path and honest audit; XML lint PASS is insufficient.

**Example:** A release report distinguishes verified source ISO, staged configuration files for the owner-prepared USB, VM live evidence, physical SSD preflight, post-install and owner-secret actions, and bare-metal security acceptance. It does not require a USB image generator.
