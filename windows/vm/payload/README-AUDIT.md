# Installed Windows audit — independent of the VM and ChatGPT

**Portable, stock-Windows package:** copy these four files into one folder
on a USB drive (or another readable local directory):

- `RUN-AUDIT.CMD` — entry point; asks for UAC as required, then opens the report.
- `run-audit.ps1` — collects, evaluates, and stores reports locally.
- `audit.ps1` — canonical Windows-native evidence collector used on VM and ASUS.
- `evaluate-audit.ps1` — local Windows-native evaluation, including explicit
  `NOT_PROVABLE` gates, without Python, Oracle, guest credentials or network.

On the **installed Windows 11 Pro**, double-click `RUN-AUDIT.CMD` and approve
the Windows UAC elevation prompt. No commands, internet or ChatGPT session
are required. This is **not** the WinPE audit (`windows/vm/winpe-audit/AUDIT.CMD`),
which must only run in the installer environment.

A human-readable report opens automatically in Notepad, and is always saved as:

```text
C:\ProgramData\DesktopWindows\Audit\report.txt
C:\ProgramData\DesktopWindows\Audit\result.json
C:\ProgramData\DesktopWindows\Audit\facts.json
C:\ProgramData\DesktopWindows\Audit\runs\<timestamp-id>\
```

`report.txt` contains an overall verdict, exact PASS/FAIL/NOT_PROVABLE
counts and every check name; for failures it includes the expected condition.
`result.json` includes the check evidence and evaluation. `facts.json` has
raw observations from the actual Windows OS. Previous runs remain available
in `runs\`. The report is **not** hidden in `%TEMP%`.

On the **physical ASUS** the software auditor cannot certify physical-only
requirements such as ESS, DRTM, external Ledger, hardware recovery flow and
SSD1 independence; they appear as `NOT_PROVABLE_MANUAL` and prevent the
overall status from becoming `PASS`. `INCOMPLETE` is not release approval.

In the VirtualBox test the same local report is generated directly by Windows.
The optional `live_audit.py` mechanism merely launches/collects from the VM;
it is neither installed nor required on ASUS.

Read-only audits never provision disks, keys, TPM enrollments or software.
