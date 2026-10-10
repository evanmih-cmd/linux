# Windows workstation

This directory contains the Windows 11 Pro security-workstation design and test bench.

- `BUSINESS_REQUIREMENTS.md` — authoritative product requirements for the Windows workstation.
- `ARCHITECTURE.md` — selected Windows security architecture and validation model.
- `ASUS_RELEASE_AUDIT.md` — evidence-backed NO-GO/GO audit, 36-requirement traceability, and the current physical-installation blockers. A structural contract PASS is not release authorization.
- [Portable installed-Windows audit](vm/payload/README-AUDIT.md) — run `RUN-AUDIT.CMD` locally on VM **or ASUS**; `report.txt` is retained under `C:\ProgramData\DesktopWindows\Audit\`, independent of ChatGPT, Linux, or Guest Control.
- `vm/` — repeatable VirtualBox test bench tracked by GitHub issue #6.
- Bare-metal ASUS implementation remains tracked by GitHub issue #5.

The Windows VM bench uses the existing VirtualBox SOAP/WebService control path. Hyper-V is not a test-bench dependency.

The frozen Linux portable-workstation work remains under `portable/` as a fallback and research record; it is no longer the production architecture.
