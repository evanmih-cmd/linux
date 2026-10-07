# Windows security workstation — architecture

## Status and authority

This document defines the current technical architecture for the Windows security workstation.

The authoritative product requirements are in
[`BUSINESS_REQUIREMENTS.md`](BUSINESS_REQUIREMENTS.md). If this architecture
conflicts with a business requirement, the requirement wins and this document
must change.

The previous Linux portable-workstation design remains preserved under
`portable/` as a proven fallback and research record. It is no longer the
production architecture for this workstation.

The architecture is deliberately **Product First** and **Economy First**:

- **Product First** means supported product mechanisms are evaluated before we
  build substitutes. It does not mean custom work is forbidden.
- **Economy First** means total lifecycle cost matters: implementation effort,
  repeated administration, recovery burden, debugging time, hardware cost,
  update burden and expected failure cost. It does not mean "fewest
  components at any price".
- A built-in feature does not win merely because it is built in; it wins when
  it satisfies the requirements at lower lifecycle cost.
- Custom code is acceptable when the platform has a real gap and the custom
  component can be kept narrow, auditable and cheaper than the alternatives.
- Preview/beta/test-only functionality is not a production dependency unless a
  requirement explicitly accepts that risk.

The architecture intentionally separates:

1. **software/configuration proof** developed in the VirtualBox bench (#6);
2. **hardware/security-boundary proof** performed on the ASUS (#5).

A VM result is never promoted into evidence for a hardware-specific claim that
the VM cannot faithfully model.

## Architecture decision

The production platform is **Windows 11 Pro on the second internal SSD of the
ASUS TUF A14 FA401EA**.

The key product change from the Linux design is intentional:

- portability of the complete OS between arbitrary hosts is no longer a
  requirement;
- the primary ASUS may be part of the trust architecture;
- the workstation is treated primarily as a **user identity, credential and
  authorization endpoint** for cloud and high-value services;
- the ordinary desktop OS is not treated as the only security boundary;
- long-lived secrets should live behind independent hardware/VBS trust
  boundaries where the platform supports that model.

This makes supported Windows mechanisms such as BitLocker, TPM/Pluton,
Windows Hello, Enhanced Sign-in Security, Virtualization-Based Security,
Hypervisor-protected Code Integrity and VBS enclaves first-class architectural
building blocks instead of recreating equivalents in the desktop OS.

## Primary hardware and workload

Primary machine:

- ASUS TUF A14 FA401EA;
- AMD Ryzen AI MAX+ 392 / Zen 5;
- two internal M.2 slots;
- built-in ASUS FHD webcam and IR camera;
- Microsoft Pluton security processor present on the platform;
- existing Windows 11 Home installation on SSD1;
- Windows 11 Pro production installation on SSD2.

The workload is intentionally narrow:

- browser-centric access to cloud services;
- password/passkey and other credential use;
- crypto/wallet extensions;
- Ledger-backed transaction signing;
- other potentially irreversible high-value actions;
- ordinary administration required to keep the workstation secure and usable.

The workstation does **not** need to be optimized as a generic local compute
server. Cloud storage and remote services may hold the bulk of working data.
The local machine's distinctive value is its ability to:

- establish user identity;
- protect device-bound secrets;
- authorize use of credentials;
- provide trusted or stronger-than-normal execution domains;
- mediate access to external hardware roots of trust.

## Selected Windows edition and install language

Production edition:

- **Windows 11 Pro**;
- standard edition, **not N**;
- base language **English (United States)**.

The N edition is not selected because removing and later reconstructing media
framework dependencies creates unnecessary product risk around camera,
biometrics and related desktop components without providing a security benefit.

Region, keyboard, time zone and date/currency formats are independent of the
base OS language and may be configured for Germany or user preference.

License activation is separate from software provenance. A product key may
activate the OS, but activation is not evidence that the installation media is
authentic.

### License procurement is not a security boundary

Retail is preferred when its transferability is worth the price difference;
OEM is acceptable when the savings justify binding the license to this ASUS.
A cheap secondary-market key may be an economic choice with provenance/revocation
risk, but it must never change the software-source rule: the OS image still
comes only from Microsoft. VM-bench activation is not required for configuration
proof.

A second independently installed Windows instance is treated as a separate
licensing question rather than assuming that inability to boot two bare-metal
instances simultaneously grants a second license.

## Installation-media trust

Only an official Microsoft Windows 11 ISO is an accepted OS source.

Current verified bench artifact:

- file: `Windows11_Client_x64_en-us_26300_9457.iso`;
- size: `9047330816` bytes;
- SHA-256:
  `BD4307DF32BC8AF33B39CCECB1174AEB345386630F89A2B86C7A4E36B55EA650`.

The recorded provenance is in
[`vm/ISO_PROVENANCE.md`](vm/ISO_PROVENANCE.md).

Required media workflow:

```text
Microsoft download
        ↓
SHA-256 comparison with Microsoft-published value
        ↓
verified ISO
        ↓
VM install or physical installation media
        ↓
Secure Boot / Trusted Boot runtime chain
```

SHA-256 verification and Secure Boot solve different problems:

- SHA-256 proves the ISO matches the official published image;
- Secure Boot/Trusted Boot protect executable boot/runtime components when the
  machine starts.

Do not download Windows ISO images, installers, "activation helpers", custom
images, driver packs or scripts from license-key resellers.

## Security objective

The core security objective is **compartmentalization**.

The design explicitly rejects this model:

```text
ordinary Windows root/SYSTEM/kernel
        ↓
absolute access to every user secret
```

The desired model is:

```text
hardware / hypervisor security boundaries
        ↓
multiple independent trust domains
        ↓
ordinary Windows VTL0 desktop
```

Compromise of one domain should grant the attacker that domain's authority, not
automatically all user identities and long-lived keys.

Examples of intentionally distinct domains:

- BitLocker + TPM/Pluton boot release;
- Windows Hello keys;
- ESS biometric sensor/matcher path;
- VBS/VTL1 isolated code and data;
- YubiKey recovery key material;
- Ledger transaction-signing keys;
- browser sessions and extension state in ordinary VTL0.

No single software layer is expected to make all other factors irrelevant.

## Threat model

The architecture is designed to preserve useful security properties under
stronger compromise than "one normal user process is malicious".

Relevant attacker classes include:

1. malicious web content or browser extension;
2. malware running as the interactive user;
3. elevated administrator/SYSTEM compromise;
4. arbitrary ordinary Windows kernel/VTL0 compromise;
5. theft of either SSD;
6. replacement or modification of boot artifacts;
7. loss or destruction of the ASUS/TPM;
8. malicious host-side calls into a legitimate enclave API.

The architecture does **not** claim that an already-compromised ordinary OS can
safely display arbitrary transaction context. That is the trusted-context gap
covered later in this document.

The architecture also does not treat firmware/SMM compromise as harmless.
Secure Launch/DRTM reduces the amount of early boot software that must be
trusted for the VBS launch measurement, but hostile platform firmware below or
outside that boundary remains a separate class of risk.

## Trust-domain map

The intended high-level security layout is:

```text
ASUS hardware
│
├── TPM / Microsoft Pluton
│     ├── device-bound key protection
│     ├── BitLocker protector state
│     └── Windows Hello key protection
│
├── IR camera + ESS-capable device path
│     └── biometric input for Windows Hello
│
├── CPU virtualization / hypervisor boundary
│     ├── VTL1 / Secure Kernel / protected services
│     │     └── optional VBS enclave credential broker
│     │
│     └── VTL0
│           ├── Windows kernel
│           ├── SYSTEM/admin services
│           ├── Chrome
│           ├── wallet extensions
│           └── ordinary applications
│
├── YubiKey (offline/recovery domain)
│     └── non-exportable recovery private key
│
└── Ledger (transaction-signing domain)
      └── crypto private keys + trusted device display
```

The exact internal Windows implementation of TPM/Pluton, Hello, VBS and ESS is
owned by the platform. The project configures and verifies those mechanisms; it
does not replace them.

## Physical disk and boot layout

### Two-SSD model

The intended physical layout is:

```text
SSD1
└── existing Windows 11 Home
    ├── its own EFI/boot state
    ├── its own Windows RE state
    └── Device Encryption / BitLocker technology

SSD2
└── Windows 11 Pro security workstation
    ├── GPT
    ├── dedicated EFI System Partition
    ├── Microsoft Reserved partition as required
    ├── BitLocker-protected OS volume
    └── dedicated Windows RE partition
```

SSD2 should receive its own ESP and recovery structures so it can be erased,
reinstalled or removed without creating a boot-repair dependency on SSD1.

This is primarily an **independence and recovery** property. A separate ESP is
not treated as a confidentiality boundary because a sufficiently privileged
attacker can modify storage that the running OS can access.

### Installation isolation

During physical Windows 11 Pro installation, SSD1 should be made **offline in
WinPE/Setup** before destructive partitioning begins.

Physical removal of SSD1 is not required.

The installation process must fail safely if disk identity is ambiguous. Do not
guess by drive letter, display order, or approximate size when a destructive
operation is involved.

### No cross-OS auto-unlock

Booting one Windows installation must not automatically unlock the other OS
volume.

Do not configure BitLocker auto-unlock between the Home and Pro OS volumes.

A TPM does not make every encrypted OS volume automatically available merely
because the same physical TPM is present. Each OS volume follows its own
protector/boot policy.

If the Home SSD is intentionally left unencrypted, a Pro administrator could
read its NTFS contents; therefore Home encryption should remain enabled when
that SSD contains data whose at-rest confidentiality matters.

## Normal boot path

The production boot path is conceptually:

```text
UEFI firmware
        ↓
Secure Boot
        ↓
Windows Boot Manager / trusted boot chain
        ↓
BitLocker TPM policy + startup PIN
        ↓
OS volume release
        ↓
Windows hypervisor / VBS launch
        ↓
Secure Kernel / VTL1
        ↓
ordinary Windows VTL0
        ↓
Windows Hello / ESS for in-OS identity
        ↓
sensitive workload
```

The exact ordering of internal measured-boot and hypervisor initialization is
owned by Windows; this diagram expresses trust boundaries and user workflow,
not an implementation-level boot trace.

## BitLocker

### Production protector

The Windows 11 Pro OS volume uses:

```text
TPM + startup PIN
```

for the normal preboot path.

The startup PIN is an **early-boot credential**, entered before ordinary
Windows applications are running. It is not reused as a routine application or
desktop authentication secret.

TPM anti-hammering and BitLocker policy provide a materially different security
model from storing a short reusable PIN as a normal password hash.

### Recovery

Maintain a BitLocker recovery key offline, outside the laptop.

The recovery key is exceptional recovery material, not a normal daily
credential.

An unexpected BitLocker recovery event is a security signal, not merely an
annoying password prompt. If there is no understood benign cause, the preferred
response is to stop, use trusted recovery/install media, investigate/rebuild,
and avoid feeding recovery material into an environment whose boot integrity is
in doubt.

Recovery material must not be emitted into automated logs, Git, issue comments
or VM run artifacts.

### Post-compromise BitLocker rule

BitLocker is an **offline/boot confidentiality boundary**, not a security
boundary against an already-hostile Windows VTL0.

An attacker with administrator/SYSTEM or kernel-level authority in the running
OS must be assumed able to inspect and modify the BitLocker protector set,
including obtaining an existing numerical recovery password when such a
protector is present or adding a new recovery protector under attacker control.

Therefore any credible administrator/SYSTEM/kernel compromise invalidates trust
in the current BitLocker protector set. A later clean-looking reboot with
TPM + startup PIN does **not** re-establish trust in that encrypted volume.

Recovery from such a compromise requires a cryptographic reset of the OS volume:

```text
suspected hostile VTL0
        ↓
boot trusted external installation/recovery media
        ↓
wipe/recreate the Windows OS volume
        ↓
create a new BitLocker volume/master-key state
        ↓
create fresh protectors and re-enroll TPM + startup PIN
        ↓
fully update, configure and audit
```

Rotating only the recovery password, removing malware, or reinstalling Windows
over the existing encrypted volume is not sufficient for this threat model.

Offline copies of BitLocker recovery material remain useful for availability
and ordinary recovery, but they are **not** an independent secret domain
protected from hostile VTL0.

### Separate Hello PIN

The Windows Hello PIN remains available as fallback when biometric login is
unavailable.

The Hello PIN is device/TPM-bound authorization, not an ordinary reusable
password hash. However, its digits are still entered through the running OS,
so the architecture does not claim that PIN entry is invisible to an already
hostile VTL0 kernel. This is another reason ESS Face is the preferred normal
in-OS path.

For compartmentalization, it should be **distinct from the BitLocker startup
PIN**. Reusing the preboot PIN in normal userspace would unnecessarily expose
the same secret to a larger attack surface.

Normal daily intent is therefore:

```text
boot: BitLocker startup PIN
desktop/app authorization: ESS Face
fallback only: distinct Hello PIN
```

This accepts two memorized PINs in exchange for keeping the high-value preboot
secret out of normal userspace. The Hello PIN should be needed rarely if ESS
Face works reliably.

## TPM and Microsoft Pluton

Pluton/TPM is a hardware root for device-bound keys, measured policy and
hardware-protected key operations.

The architecture uses it for platform functions such as:

- BitLocker protector policy;
- Windows Hello keys;
- device-bound key protection and attestation where the platform uses it.

Pluton is not treated as a replacement for VBS. They solve different problems:

- TPM/Pluton protects device-bound key material and key operations;
- VBS creates isolated execution/memory domains that remain meaningful even
  when ordinary VTL0 is compromised.

The design should prefer supported Windows abstraction layers over
project-specific direct TPM plumbing unless a concrete platform gap requires
otherwise.

## Virtualization-Based Security

### VTL0 is not the final trust boundary

Ordinary Windows kernel, drivers, SYSTEM services and applications run in the
normal world, conceptually VTL0.

VBS uses the Windows hypervisor to create a stronger isolation boundary for
VTL1/Secure Kernel/protected services.

The architecture relies on the property that arbitrary VTL0 kernel compromise
does not automatically imply direct read/write access to private VTL1 memory.

That does **not** mean a compromised VTL0 is powerless. It can still:

- control ordinary UI;
- invoke exposed enclave entrypoints;
- manipulate browser state;
- perform denial of service;
- attempt confused-deputy attacks;
- steal plaintext that an application legitimately receives in VTL0.

This distinction between **memory confidentiality** and **authorized-oracle
abuse** is fundamental to the vault design.

## HVCI / Memory Integrity

Hypervisor-protected Code Integrity / Memory Integrity is part of the production
baseline.

Its purpose is to move Code Integrity enforcement into the VBS-protected
security architecture and reduce the ordinary kernel attack surface, including
known vulnerable-driver paths and writable/executable kernel memory abuse.

It is a hardening layer, not a substitute for the stronger secret boundaries
provided by TPM/Pluton, ESS, VBS enclaves, YubiKey or Ledger.

## Secure Launch / DRTM

Enable and verify **System Guard Secure Launch / DRTM** on the physical ASUS
when supported by the final firmware/build configuration.

The useful property is concrete:

- ordinary UEFI firmware executes first;
- a dynamic root-of-trust launch resets/re-establishes the dynamic measurement
  chain for the protected Windows hypervisor/Secure Kernel launch;
- the VBS launch therefore does not need to trust the entire enormous early
  firmware execution history in the same way a purely static measurement chain
  would.

Secure Launch does not make compromised SMM/firmware harmless. It narrows the
trusted launch boundary; it does not eliminate platform-firmware risk.

VirtualBox evidence is not accepted as proof of real ASUS DRTM behavior.

## Windows Hello and Enhanced Sign-in Security

### Normal identity path

Windows Hello is the primary in-OS user-verification mechanism.

Normal user-verification preference:

```text
ESS Face
  ↓
Windows Hello
  ↓
hardware-backed user authorization
```

The Hello PIN is fallback, not the preferred routine prompt.

### ESS is already evidenced on this ASUS

ESS support on the target is not merely inferred from "IR camera" marketing.

The existing Windows 11 Home installation has produced Windows Biometrics
Operational event 1108 messages showing:

- the facial-recognition software device isolated in a
  **Virtual Secure Mode** process;
- the Windows Hello Face bootstrap/virtual software path as expected.

A capability check also showed the built-in ASUS IR/FHD camera and the relevant
USB host-controller path advertising the secure-device capability.

The event stream also contains a Windows Hello Face virtual/bootstrap software
device running in Local System. That does not negate the ESS result: the
security-relevant facial-recognition path is the separate device explicitly
reported as isolated in a **Virtual Secure Mode** process.

Therefore the production architecture treats **ESS Face on the built-in camera
as an already demonstrated machine capability**, to be re-verified after the
Windows 11 Pro installation.

External cameras are not assumed to provide the same ESS path.

### What Hello proves and what it does not

Windows Hello/ESS provides strong user presence/identity verification and
hardware-backed key authorization.

It does **not** by itself prove that the user knowingly approved an arbitrary
application-specific semantic such as:

```text
"release the Binance password"
```

rather than:

```text
"release the Amazon password"
```

The architecture therefore distinguishes:

- **identity/presence** — what Hello/ESS is good at;
- **trusted transaction context** — a separate problem.

Do not claim that a caller-supplied string in a normal Hello/consent UI is
cryptographically bound to a VBS-enclave request unless the platform API
explicitly provides and documents that binding.

## Administrator Protection

Use **Windows Administrator Protection** when available and supported on the
installed Windows 11 Pro build.

The intended model is a deprivileged normal session with just-in-time elevation
for administrative operations, with Windows Hello used for the elevation
authorization path.

Administrator Protection is architecturally preferable to treating a
permanently elevated administrator token as the normal desktop identity.

Important boundary statements:

- classic UAC/Secure Desktop protects against ordinary user-mode UI spoofing,
  but it is not a security boundary against an already-hostile kernel;
- Administrator Protection is a distinct modern mechanism;
- do **not** describe Administrator Protection itself as "running in VBS"
  unless Microsoft explicitly documents that implementation;
- the design may benefit from VBS/ESS overall without conflating those
  mechanisms.

## Credential Guard

Credential Guard is **not a production requirement** for this standalone
workstation.

Its main value is protecting domain authentication material such as Kerberos
and NTLM secrets. That is not the dominant secret class for this standalone
crypto/cloud workstation.

Do not buy a higher Windows edition or redesign the machine merely to obtain
Credential Guard.

If it is available under the final supported configuration at zero meaningful
cost, enabling it may be considered separately, but it is not part of the core
acceptance gate.

## App Control / WDAC

Application Control can reduce executable and driver attack surface and may be
useful later.

It is not the primary solution for the browser-extension threat:

- an allowed Chrome process can still execute a malicious allowed/installed
  extension;
- a malicious extension update remains a supply-chain problem inside the
  allowed browser.

The initial architecture therefore prefers:

- a dedicated sensitive Chrome profile;
- a small manual allowlist of required wallet extensions;
- no unnecessary extensions;
- normal browser/vendor update channels;
- Ledger verification for irreversible crypto actions.

Do not introduce a heavy corporate App Control management stack unless its
marginal security value justifies the operational cost.

## Windows Sandbox

Windows Sandbox may be used for opening unknown/untrusted files when useful.

It is a convenience isolation tool, not part of the credential root of trust
and not a substitute for VBS-enclave, YubiKey or Ledger boundaries.

## Credential strategy

### Prefer non-password credentials where services support them

Passkeys/WebAuthn/client-key authentication are preferable to passwords because
a private key can remain hardware/device bound and need not be exposed as a
reusable plaintext credential.

Windows Hello is therefore preferred for passkey-style user authentication
where the service supports it.

A password is fundamentally weaker at the moment of use: to fill a password
into Chrome, plaintext eventually exists in ordinary VTL0/browser memory.

The architecture does not pretend otherwise.

### Browser password reauthentication

Chrome's supported "use Windows Hello when filling passwords" behavior is
useful at the ordinary-user/same-session layer and matches the desired UX of
fresh user presence before credential use.

It is not, by itself, the final defense against an already-hostile VTL0 kernel.

The stronger long-lived-secret objective is handled by the VBS credential
broker design below.

## VBS credential broker / vault

### Scope

Do **not** build a complete password manager.

Do not build:

- a new sync service;
- a new browser UI ecosystem;
- a new general password database format unless unavoidable;
- custom cryptographic primitives;
- a general desktop secret-service replacement.

Build, if the proof validates the economics, only a **small VBS-enclave
credential broker/policy component** that addresses the specific platform gap:
protecting the master credential secret and preventing silent bulk export from
VTL0.

### Security objective

The target split is:

```text
VTL1 / VBS enclave
    ├── vault master K
    ├── record decryption
    ├── authorization policy
    ├── sealing / identity checks
    └── recovery-key unwrap path

VTL0 host
    ├── UI
    ├── browser integration
    ├── encrypted vault blob
    └── untrusted transport
```

The host may be malicious.

The security claim is **not** "malicious VTL0 cannot call the enclave".

The claim is:

- malicious VTL0 cannot directly read enclave memory or export K;
- there is no bulk plaintext-dump API;
- the enclave exposes only narrow, policy-checked operations;
- each credential release is deliberate at the enclave API level;
- long-lived master material remains outside VTL0.

### Master key

Generate a random **256-bit master key K** using the supported system CSPRNG in
the trusted implementation path.

Do not derive K from:

- the BitLocker startup PIN;
- the Hello PIN;
- a user password;
- MAC addresses, clocks or other hand-mixed local entropy.

No "move the mouse for entropy" ceremony is required for a normal system CSPRNG
after initialization.

### Normal user-bound protection

The daily path should use the supported Windows Hello / VBS user-bound
mechanism rather than inventing a second owner-managed TPM wrapper.

Conceptually:

```text
Windows Hello / user-bound authorization
        ↓
VBS enclave can use/unseal K
        ↓
one-record operation
```

The implementation must not reduce this to:

```text
untrusted host says hello_ok=true
```

A host-provided boolean is not a security boundary.

Use the supported VBS-enclave/Windows-Hello user-bound pattern or equivalent
documented mechanism so that the authorization decision is not merely trusted
because VTL0 claimed it succeeded.

### Narrow API

There must be no:

```text
ExportKey()
DumpVault()
GetAllPlaintext()
```

baseline entrypoint.

The minimal public surface should look conceptually like:

```text
ReleaseCredential(record_id, fresh_authorization)
UpdateCredential(record_id, encrypted_input, authorization)
RecoverVault(recovery_authorization)
```

Only operations actually needed by the product should exist.

Metadata may remain outside the enclave if disclosure of that metadata is
acceptable. Secret values and K do not.

### Host compromise and oracle abuse

A malicious VTL0 host can:

- call legitimate enclave entrypoints;
- lie in its own UI;
- request a different record than the user intended;
- replay allowed requests unless nonce/state policy prevents it;
- instantiate another host process around the same enclave code;
- deny service.

Therefore enclave security must not depend on:

- host process identity;
- "SYSTEM only" checks;
- a particular PID;
- UI text drawn by the host.

This is why enclave identity, request binding and anti-replay state matter.

### Enclave identity and sealing

Use restrictive enclave identity/sealing policy.

The design must explicitly decide and document use of the supported identity
policy dimensions rather than accepting a permissive "anything signed by us
forever" rule. Relevant policy classes include concepts such as
`EXACT_CODE`, `SAME_PRIMARY_CODE`, `SAME_IMAGE`, `SAME_FAMILY` and
`SAME_AUTHOR`; the most permissive policy is not the default choice merely
because upgrades become easier.

Versioning must include an anti-rollback story.

A hostile host must not be able to restore an old vulnerable enclave + old
sealed state and silently regain a previously removed capability.

The exact supported VBS enclave identity policy is an implementation decision,
but it must be reviewed before production.

The implementation should start from Microsoft's supported VBS-enclave tooling
and user-bound/Windows-Hello examples (including the HostAppUserBound pattern)
rather than inventing the host/enclave authorization handshake from scratch.
Production enclave binaries must also follow the platform's enclave integrity,
CFG and signing requirements; debug/test signing is not a production trust
model.

### Plaintext-at-use limitation

When a password is legitimately released to Chrome, that specific plaintext
password exists in VTL0.

Therefore a hostile Windows kernel can potentially steal **that credential at
the moment it is used**.

The VBS-vault objective is narrower and still valuable:

```text
hostile VTL0
    ≠ automatic master-key theft
    ≠ automatic bulk vault dump
    ≠ automatic access to every never-used credential
```

This is why passkeys/hardware-bound keys remain preferable whenever available.

## Trusted-context gap

### The remaining problem

Suppose the user is present and ESS verifies them.

A malicious VTL0 host could still attempt:

```text
enclave request: release Binance
host UI:          "Authenticate for Amazon"
user:             Face verified
```

If the authorization result is not cryptographically bound to the enclave's
exact `record_id`, presence alone does not prove transaction intent.

A generic third-party VBS enclave cannot simply draw arbitrary pixels through a
trusted VTL1 display path. Its restricted runtime is not a normal desktop
process: it does not get ordinary user32/GDI/DWM UI or direct arbitrary device
I/O. Any screen/device interaction normally has to be mediated by the untrusted
host side.

Secure Desktop is not considered sufficient against hostile VTL0 kernel code.

### Version 1 accepted compromise

The initial production architecture may proceed without a generic trusted
display.

Version 1 therefore accepts a residual **confused-deputy/oracle** risk while
the user is actively present.

This is acceptable only if the stronger properties remain true:

- K stays out of VTL0;
- bulk export is impossible through the normal API;
- credential release requires fresh user verification;
- release is one-record-at-a-time;
- rate/replay/state controls are explicit;
- the residual risk is documented rather than disguised as solved.

Trusted display is a hardening phase, not a blocker for the first useful
system.

## Phase 2 external trusted display

Research a small external device acting as a trusted semantic display and
physical confirmation channel.

Conceptual device:

```text
MCU
+ small display
+ physical button
+ device key
+ USB/serial transport
```

The USB/serial transport may be fully hostile.

Security comes from authenticated content, not trusted transport.

### Candidate protocol

1. external display generates a fresh nonce;
2. untrusted VTL0 transports the nonce to the enclave;
3. enclave constructs a request such as:

```text
{
  op: "release",
  record: "binance.com",
  nonce: <display nonce>,
  request_id: <fresh id>
}
```

4. enclave authenticates/signs the request;
5. VTL0 transports it to the display;
6. display verifies the enclave/broker identity and signature;
7. display shows the authenticated record/action;
8. user presses the physical button;
9. display produces an authenticated ACK bound to the same
   `nonce + record + request_id`;
10. enclave verifies the ACK before releasing the credential.

If VTL0 changes `binance.com` to `amazon.com`, signature verification fails.

If VTL0 replays an old confirmation, nonce/request binding fails.

If VTL0 drops or delays traffic, the result is denial of service, not silent
semantic substitution.

### Key establishment

The phase-2 design must include a real provisioning story for mutual identity:

- how the display knows the legitimate enclave/broker public identity;
- how the enclave knows the legitimate display identity if ACKs are signed;
- how replacement/recovery works;
- how old devices/keys are revoked.

Do not treat "USB device connected" as identity.

## YubiKey recovery architecture

A YubiKey-class token is the preferred independent recovery factor for the new
Windows design.

The existing Rutoken is **not** a production dependency for this architecture.
It may remain useful for unrelated existing signing keys, but the Windows
workstation should not contort itself around it. Existing Rutoken signing/key
containers are not to be modified, migrated or repurposed merely to satisfy
this workstation design.

### Daily use

YubiKey is **not required for normal daily login or credential release**.

Normal path remains:

```text
BitLocker startup PIN
→ Windows
→ ESS Face / Windows Hello
→ normal application authorization
```

If the camera fails, Hello PIN is the built-in fallback.

There is no v1 requirement to implement a custom Windows Credential Provider or
make YubiKey a mandatory local-login mechanism. Native Windows FIDO2/security-
key sign-in is not assumed to be a standalone local-account replacement; if a
future requirement wants token-based local login, Yubico's supported login
product or another documented path must be evaluated separately instead of
pretending the Settings "Security key" page automatically solves local login.

### Vault recovery

The vault must have a recovery path independent of the ASUS TPM/Pluton.

Candidate design:

```text
vault master K
├── normal user-bound VBS/Hello protection on ASUS
└── recovery wrapper encrypted to YubiKey-held asymmetric key
```

The YubiKey private key must be generated/held as non-exportable token key
material.

Recovery then requires possession of the YubiKey plus its local authorization
(PIN/touch as appropriate to the selected application/protocol).

The exact YubiKey model and interface (for example PIV for asymmetric
unwrap/decrypt/sign capability, FIDO2 for service authentication) are selected
after the base Windows and vault PoC are proven.

Do not assume FIDO2 by itself is an arbitrary general-purpose decryption API.

The recovery token should normally be stored separately from the laptop.

## Ledger / wallet architecture

Ledger is an independent transaction-signing trust domain.

For Ledger-backed accounts:

- the seed/private key remains on Ledger;
- MetaMask/Phantom/other wallet extensions are interfaces, not key custody;
- do not import the real Ledger seed into a browser/software wallet;
- do not import a software-wallet seed into Ledger merely to make the accounts
  look equivalent;
- verify recipient, amount and action on the Ledger display;
- keep blind signing disabled by default;
- enable blind signing only for a specific protocol when strictly required and
  with explicit understanding of the lost display assurance.

A compromised browser/extension/Windows VTL0 may:

- alter dApp UI;
- substitute destination data before signing;
- manipulate session state;
- attempt malicious transaction payloads.

It still should not be able to extract the Ledger private key.

For irreversible crypto actions, the Ledger display is the trusted semantic
confirmation path available today.

## Browser model

Chrome is the required browser for the sensitive crypto/wallet workload.

Use a dedicated sensitive Chrome profile with:

- only required wallet/crypto extensions;
- no extension sync with unrelated profiles;
- minimal general web browsing;
- official Google update channel;
- Windows Hello reauthentication where supported and useful.

Ordinary browsing should use a separate browser/profile so arbitrary browsing
state, cookies, downloads and extensions do not accumulate in the sensitive
profile. The exact general-purpose browser is not currently an architecture
constraint.

The user may serve as the wallet-extension allowlist. A large enterprise browser
policy framework is not required merely to encode the same tiny list unless
automation later provides a clear lifecycle advantage.

## Software provenance and channels

Security-critical executable software should come from authoritative vendor
channels:

- Windows / Windows Update: Microsoft;
- Chrome: Google;
- ASUS device/firmware software: Microsoft Update and/or ASUS-supported
  channels as justified;
- YubiKey software/firmware/tools: Yubico;
- Ledger firmware/software: Ledger-supported channel;
- wallet extensions: official extension-store publisher identities and project
  provenance.

Do not install alternate "driver updater", "security optimizer", activation or
download-wrapper utilities.

## Update and maintenance model

### Supported vendor updaters, not a custom package manager

Windows owns OS/security maintenance.

Chrome owns Chrome update delivery through its supported vendor channel.

Defender/signature/platform updates remain on supported Microsoft mechanisms.

The project may add **policy glue and audit**, but it must not build a parallel
package-management ecosystem.

### Sensitive-work gate

Sensitive work must not begin while the machine is knowingly outside required
security maintenance policy.

The desired startup/session policy is:

```text
boot
  ↓
network available
  ↓
check required security/update state
  ↓
pending required update/reboot?
  ├── yes → apply/complete update and reboot if required
  └── no
  ↓
verify security posture
  ↓
release sensitive workload
```

The user should receive a clear state such as:

- current / safe to proceed;
- updated successfully / reboot required or completed;
- update/security gate failed.

Recovery/admin access does not need to be blocked merely because sensitive
work is gated.

Do not turn this policy glue into a replacement for Windows Update.

### Reboots

A real Windows reboot is acceptable and expected after security/platform
updates.

Unlike the old portable Linux design, there is no requirement to preserve an
external one-time firmware boot selection across restart.

## Defender and firewall

Windows Defender and Windows Firewall remain enabled as platform baseline
protections unless a concrete supported replacement is selected.

Do not weaken these controls merely to make wallet/browser tooling easier.

Any exception must be narrow, documented and tied to a demonstrated workload
requirement.

## Recovery and rebuild

The Windows OS is considered **disposable system state**.

If the system becomes untrusted or badly damaged, the preferred security
recovery is often:

```text
power off
↓
boot trusted Microsoft installation/recovery media
↓
wipe/reinstall Windows 11 Pro on SSD2
↓
fully update / restore supported configuration
↓
re-establish Windows Hello / ESS
↓
restore cloud/app state
↓
recover vault using independent recovery factor if TPM-bound state is gone
↓
resume sensitive work only after audit passes
```

There is no requirement to preserve a compromised Windows system instance.

For administrator/SYSTEM/kernel compromise, "rebuild" specifically means
recreating the encrypted OS volume and its BitLocker key/protector state, not
merely reinstalling into or cleaning the existing BitLocker volume. This makes
any recovery credential or protector state captured by the compromised OS
irrelevant to the newly created volume.

The design favors clean supported rebuild over elaborate attempts to salvage a
security-compromised OS.

### Recovery material

Keep offline, outside normal machine state:

- BitLocker recovery key;
- vault/YubiKey recovery factor;
- any service-level recovery codes that are required;
- installation-media provenance/checksums as practical.

Recovery material must not all live in the same stolen laptop bag if avoidable.

## Existing Windows Home installation

The existing Windows 11 Home installation on SSD1 remains outside the security
workstation's normal runtime.

Requirements:

- preserve its ability to boot/recover independently;
- keep its own volume encryption enabled if its data matters;
- do not configure automatic unlock from the Pro environment;
- do not place required Pro boot/recovery state on SSD1;
- do not make SSD1 presence a prerequisite for Pro boot.

The Home installation is not considered a trusted recovery environment for the
Pro security workstation merely because it is on the same laptop.

Trusted recovery starts from known-good recovery/installation media.

## Provisioning architecture

### Production physical installation

The physical provisioning flow is:

```text
verify official Microsoft ISO
        ↓
create trusted installation media
        ↓
boot WinPE/Setup
        ↓
identify SSD1 and SSD2 unambiguously
        ↓
set SSD1 offline
        ↓
install Windows 11 Pro to SSD2
        ↓
allow Setup to create SSD2 GPT/ESP/WinRE
        ↓
first boot
        ↓
supported drivers + Windows Update
        ↓
apply desired security/configuration state
        ↓
enable/configure BitLocker TPM+PIN
        ↓
configure Hello/ESS and security features
        ↓
install workload software
        ↓
run machine-readable audit
```

Network availability is not required to **begin** trusted installation.

Network use after the fresh OS is running is acceptable and desirable for
supported Windows updates, drivers, activation and vendor software.

### Declarative preference

Use supported Windows unattended/setup mechanisms and PowerShell/Windows
configuration interfaces.

Manual GUI steps should exist only when the product deliberately requires user
presence or a supported API is unavailable.

The configuration source should be understandable as desired state, not a long
sequence of fragile simulated clicks.

## VirtualBox development bench

Issue #6 owns the initial Windows VM bench.

The bench deliberately uses the existing **Oracle VirtualBox SOAP/WebService**
control path.

**Hyper-V is not a dependency of the bench.**

This is an economics decision: the existing runner already has a working
VirtualBox control plane, snapshot lifecycle and automation experience.

### VM goals

The canonical VM should use UEFI firmware and, where the installed VirtualBox
SOAP/WebService stack supports them meaningfully, virtual TPM 2.0 and Secure
Boot. Their presence in the VM is useful for exercising configuration paths but
is not promoted into proof of the physical ASUS trust boundary.

The VM should prove:

- official ISO boot and unattended Windows 11 Pro installation;
- repeatable disk/layout automation;
- repeatable post-install configuration;
- browser/software install logic;
- audit logic;
- update/reboot automation;
- snapshot/reset/rebuild lifecycle;
- BitLocker policy flow to the extent VirtualBox presents a meaningful TPM;
- VBS/HVCI/Administrator Protection policy configuration where possible;
- VBS-enclave development/build/unit behavior that can run in the VM.

### VM control rules

- control VirtualBox through the existing SOAP/WebService API;
- do not assume `VBoxManage` is the control plane;
- guest work should run through repository harness/supported Windows guest
  automation;
- do not inject ad-hoc guest commands through Desktop Commander;
- Desktop Commander is acceptable for host filesystem/repository work;
- use snapshots aggressively;
- do not reinstall the VM for ordinary iteration when a clean checkpoint is
  available;
- clean old VMs/snapshots/cache artifacts so disk consumption remains bounded.

### What the VM cannot prove

The VM is not acceptance evidence for:

- real Microsoft Pluton behavior;
- the physical ASUS TPM/PCR behavior;
- ESS Face / ACPI SDEV camera path;
- real Windows Hello biometric isolation on the ASUS;
- AMD Secure Launch/DRTM on the physical CPU/firmware;
- physical dual-SSD boot independence;
- real Ledger USB/WebHID behavior;
- real YubiKey hardware behavior;
- production VBS/VTL1 resistance on the target hardware if nested
  virtualization/emulation is incomplete.

If VirtualBox cannot expose a feature faithfully, record the limitation and move
the claim to the bare-metal gate. Do not construct a mock test that merely says
PASS.

## Machine-readable audit

The same audit framework should run in VM and on bare metal.

Output should be structured and should separate:

- PASS;
- FAIL;
- NOT_APPLICABLE / NOT_PROVABLE_IN_VM;
- informational evidence.

At minimum capture:

- Windows edition/build;
- activation status (informational, not a security gate);
- UEFI/Secure Boot state;
- TPM presence/type and relevant readiness where queryable;
- BitLocker encryption/protectors without exposing recovery secrets;
- disk/partition/ESP/WinRE layout;
- VBS state;
- HVCI / Memory Integrity state;
- Secure Launch state;
- Windows Hello/ESS evidence;
- Windows Biometrics event evidence relevant to ESS;
- Administrator Protection state;
- Defender state;
- Firewall state;
- browser/software versions;
- pending update/reboot state;
- sensitive-work gate result.

The audit must never print:

- BitLocker recovery passwords;
- Hello PIN;
- startup PIN;
- vault master K;
- YubiKey PIN;
- wallet seeds/private keys;
- service passwords.

## Validation methodology

Do not confuse "configured" with "works".

Use two kinds of evidence:

1. **configuration/state evidence** — the effective policy or state is present;
2. **behavioral evidence** — the live system demonstrates the intended result.

Examples:

- BitLocker protector enumeration is configuration/state evidence;
- booting and observing a real startup-PIN prompt is behavioral evidence;
- an ESS-related registry value is not enough;
- Windows Biometrics event 1108 showing VSM isolation is runtime evidence;
- a VBS enclave API unit test is not proof that physical ASUS DRTM is active.

Use authoritative product documentation to determine expected behavior first,
then perform one meaningful end verification. Avoid repeated "try a step, see
what breaks, research the next step" loops when the supported sequence can be
determined in advance.

## Bare-metal acceptance gates

After VM configuration converges, validate on the ASUS:

1. SSD2 has independent GPT/ESP/WinRE.
2. Pro boots without SSD1 being part of its required boot chain.
3. SSD1 Home remains independently bootable/recoverable.
4. Secure Boot is active.
5. BitLocker is active on Pro with TPM + startup PIN.
6. BitLocker recovery path works from offline recovery material.
7. Home and Pro OS volumes are not automatically unlocked by booting the other
   installation.
8. VBS is active.
9. HVCI / Memory Integrity is active.
10. Secure Launch/DRTM is active when supported by the final ASUS
    firmware/Windows configuration.
11. ESS Face remains active on the built-in camera.
12. Windows Biometrics event 1108 again shows the face path isolated in Virtual
    Secure Mode.
13. Windows Hello Face works for normal in-OS user verification.
14. distinct Hello PIN fallback works.
15. Administrator Protection works with the selected Hello authorization path
    when supported by the installed build.
16. Chrome sensitive profile works.
17. required wallet extensions work.
18. Ledger works on the real USB path.
19. transaction-signing workflow leaves private keys on Ledger.
20. Windows Update/reboot preserves BitLocker, VBS, ESS and normal workstation
    usability.
21. machine-readable final audit passes all production-applicable checks.

The VBS credential broker/vault gets its own PoC and security-review gate before
it becomes responsible for real credentials.

## VBS vault PoC acceptance gates

The PoC is successful only if it demonstrates all of the following:

1. K is generated from a supported CSPRNG.
2. K is not returned to VTL0.
3. no bulk secret export API exists.
4. a host process cannot directly read enclave secret memory.
5. one record can be released through the narrow API.
6. fresh user-bound authorization is required for release.
7. the enclave does not trust a bare host boolean asserting Hello success.
8. hostile/repeated/replayed host calls are handled according to explicit
   policy.
9. sealing identity is restrictive and documented.
10. update/version/anti-rollback handling is designed before production use.
11. recovery with an independent hardware factor is demonstrated without the
    original ASUS TPM if recovery is part of the PoC.
12. the test documentation clearly states that plaintext released into Chrome
    can be stolen by a compromised VTL0 at use time.
13. the trusted-context/confused-deputy limitation is explicitly recorded.

Do not put real production passwords in the PoC.

## Non-goals / rejected baseline choices

The following are not part of the initial production architecture:

- Linux as the production daily workstation;
- portability of the complete OS between arbitrary PCs;
- Hyper-V as the VM test-bench dependency;
- Windows 11 Pro N;
- reseller-provided Windows ISO images;
- activation cracks or scripts;
- a permanently elevated daily administrator session;
- reusing the BitLocker startup PIN as the normal Hello/application PIN;
- using KWallet/desktop software storage as the root of credential security;
- tpm2-pkcs11-style custom PIN storage as a Hello replacement;
- building a full custom password manager;
- building a custom Windows Credential Provider in v1;
- requiring YubiKey for every daily login;
- requiring the existing Rutoken for the new architecture;
- treating Secure Desktop as protection against hostile VTL0 kernel;
- claiming Administrator Protection itself is VBS-resident without evidence;
- buying Enterprise merely for Credential Guard;
- treating WDAC as a solution to malicious browser extensions;
- trusting host process identity as an enclave security boundary;
- storing Ledger wallet private keys in browser extensions;
- enabling blind signing by default;
- making external trusted display a v1 blocker.

## Accepted compromises

The architecture consciously accepts:

- the complete OS is bound to the primary ASUS rather than portable;
- a specific password legitimately released to Chrome can be stolen by a
  sufficiently compromised VTL0 at the moment of use;
- ESS/Hello proves presence/identity but not arbitrary application-specific
  transaction context;
- version 1 has residual confused-deputy risk until trusted semantic display is
  added;
- physical firmware compromise remains outside what VBS/DRTM alone can fully
  neutralize;
- a VM cannot prove physical security boundaries;
- YubiKey recovery introduces a separate physical object that must be stored
  safely;
- clean rebuild is preferred over trying to preserve a compromised OS instance.

These compromises are accepted because they preserve the stronger and more
valuable properties without turning the workstation into a custom operating
system/security-platform project.

## Implementation order

1. Maintain the Windows business requirements and this architecture as the
   authority for implementation choices.
2. Complete issue #6: repeatable VirtualBox Windows 11 Pro bench using the
   existing SOAP/WebService path.
3. Build unattended installation/configuration and a reusable structured audit
   in the VM.
4. Use snapshots to converge the configuration economically rather than
   repeatedly reinstalling.
5. Install Windows 11 Pro on SSD2 of the ASUS with SSD1 offline during Setup.
6. Establish BitLocker TPM+startup-PIN, Secure Boot, VBS, HVCI, Secure Launch
   where supported, Windows Hello/ESS Face and Administrator Protection.
7. Validate the bare-metal gates once the supported configuration is complete.
8. Install/configure Chrome sensitive profile and validate Ledger + required
   wallet extensions.
9. Build the minimal VBS credential-broker PoC using fake credentials.
10. Select the exact YubiKey model/interface and prove independent vault
    recovery.
11. Decide whether the VBS broker provides enough incremental security to
    justify production use; do not force it into production merely because the
    PoC exists.
12. Research/implement the external trusted display/button protocol as phase 2
    if the residual context-spoofing risk justifies the cost.

## External architecture references

The implementation should continue to use authoritative vendor documentation as
the source for detailed platform behavior, including:

- Windows Hello / Enhanced Sign-in Security:
  https://learn.microsoft.com/windows-hardware/design/device-experiences/windows-hello-enhanced-sign-in-security
- Microsoft Pluton:
  https://learn.microsoft.com/windows/security/hardware-security/pluton/microsoft-pluton-security-processor
- VBS enclaves:
  https://learn.microsoft.com/windows/win32/trusted-execution/vbs-enclaves
- Windows boot / Trusted Boot:
  https://learn.microsoft.com/windows/security/operating-system-security/system-security/trusted-boot
- BitLocker:
  https://learn.microsoft.com/windows/security/operating-system-security/data-protection/bitlocker/
- Windows security / VBS and HVCI:
  https://learn.microsoft.com/windows-hardware/design/device-experiences/oem-vbs
