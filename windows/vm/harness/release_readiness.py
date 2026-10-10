"""Fail-closed ASUS release readiness report.

This reports current evidence; it NEVER authorizes disk destruction.
Static config PASS != VM convergence != hardware-ready installation.
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from config import Config
from media import verify_official_iso
from workflow import install_contract_check

STATUSES = ("PASS", "FAIL", "BARE_METAL_ONLY")


def review(vm_audit, *, contract, iso, cfg=None):
    cfg = cfg or Config()
    requirements = (cfg.repo / "windows/BUSINESS_REQUIREMENTS.md").read_text()
    ids = sorted(int(x) for x in re.findall(r"^### (\d+)\. ", requirements, re.M))
    expected = list(range(1, 37))
    vm_checks = {x["name"]: x["status"] for x in vm_audit.get("checks", [])}
    records = []

    def gate(name, status, proof, br):
        if status not in STATUSES:
            raise ValueError(f"unsupported gate status: {status}")
        records.append({"gate": name, "status": status, "evidence": proof,
                        "business_requirements": br})

    gate("requirements-1-to-36-traceable",
         "PASS" if ids == expected and
         sorted(int(x) for x in contract.get("business_requirements", {})) == expected
         else "FAIL", "business requirements and contract owner map are complete", list(expected))
    gate("official-microsoft-iso-sha256",
         "PASS" if iso.get("verified") is True and
         iso.get("sha256", "").lower() == cfg.official_iso_sha256.lower()
         else "FAIL",
         "source ISO SHA-256 matches the verified digest; owner creates bootable USB",
         [17, 19, 26])
    gate("vm-and-release-document-contract",
         "PASS" if contract.get("status") == "PASS"
         and contract.get("production_render", {}).get("status") == "PASS"
         else "FAIL", "Common manual-target XML + DSC structural check only; NOT live approved",
         [17, 23, 24, 35])
    gate("safe-production-installer-staging",
         "PASS" if contract.get("release_status") == "READY"
         and contract.get("production_render", {}).get("safe_for_asus_install") is True
         else "FAIL", "One canonical no-DiskID XML exists but production staging remains blocked until live two-disk acceptance",
         [2, 17, 23, 25, 36])
    gate("real-elevated-vm-security-audit",
         "PASS" if vm_audit.get("status") == "PASS" and
         vm_audit.get("facts", {}).get("AuditContext", {}).get("IsElevated") is True
         else "FAIL", "latest elevated audit has FAIL gates: " +
         ", ".join(vm_audit.get("failed", [])), [7, 9, 23, 29, 30, 32, 35])

    gate("interactive-raid-disk-selection-and-ssd1-offline", "FAIL",
         "common XML has no automatic disk targeting; real SSD1 Offline and manual LUN selection remain UNPROVEN",
         [2, 8, 25, 36])
    gate("microsoft-winre-after-windows-and-lun-growth-validation", "FAIL",
         "stock Setup owns ESP/MSR/C:/WinRE sizes; target-local layout and Microsoft-supported post-growth WinRE delete/recreate procedure not live tested",
         [2, 7, 23, 36])
    gate("production-postinstall-desired-state-executor", "FAIL",
         "staged workstation.winget is not yet bound to executable production postinstall",
         [17, 20, 21, 23, 30, 32, 36])
    gate("bitlocker-immediate-tpm-and-recovery-protectors", "FAIL",
         "FVE policies only; missing production enrollment, current VM Protection Off, protectors empty",
         [7, 9, 16, 29])
    gate("confirmed-offline-recovery-before-pin", "FAIL",
         "no owner-facing verified export and acknowledgement of recovery password",
         [9, 16, 18, 29])
    gate("owner-startup-pin-removes-tpm-only-bypass", "FAIL",
         "TPM+PIN is a policy allowance; no owner enrollment, bypass-removal, boot test",
         [9, 10, 29])
    gate("administrator-protection-enforced", "FAIL",
         f"guest TypeOfAdminApprovalMode=1; check={vm_checks.get('administrator-protection')}",
         [11, 22, 30])
    gate("windows-sandbox-feature-operational", "FAIL",
         "two WSB XML files pass guard; optional feature in VM is Disabled, runtime untested",
         [27, 32])
    gate("sandbox-internet-only-host-enforced", "FAIL",
         "networked WSB exposes unfiltered default switch; no Sandbox-specific host firewall proof",
         [4, 25, 33])
    gate("suspect-network-connection-ask-block-observability", "FAIL",
         "resmon.exe observes guest traffic but cannot enforce prompt/block or secure event log",
         [4, 27, 34])
    gate("sensitive-work-security-maintenance-boot-gate", "FAIL",
         "no fully implemented pre-work Windows Update/reboot/security-state enforcement",
         [20, 21, 22])
    gate("credential-broker-no-bulk-export-proof", "FAIL",
         "VBS vault is a planned PoC, not a deployed/reviewed broker",
         [4, 5, 12, 13, 14, 16])
    gate("asus-vbs-hvci-uefi-lock-runtime", "BARE_METAL_ONLY",
         "hardware overlay staged, physical VBS/HVCI+UEFI enrollment/reboot not proven",
         [5, 6, 24, 31])
    gate("asus-ess-face-and-hello", "BARE_METAL_ONLY",
         "ASUS IR/ESS device path and owner enrollment cannot be tested in NEM VM",
         [10, 11, 24])
    gate("asus-two-ssd-independent-boot-and-recovery", "BARE_METAL_ONLY",
         "physical SSD1/SSD2 independent ESP, boot and BitLocker recovery not tested",
         [2, 7, 8, 18, 24, 25])
    gate("ledger-yubikey-independent-hardware-path", "BARE_METAL_ONLY",
         "wallet app and six browser extensions in VM; hardware signing/recovery not tested",
         [15, 16, 24, 27, 35])
    gate("secure-launch-drtm-on-asus", "BARE_METAL_ONLY",
         "requires firmware/Windows Secure Launch runtime validation",
         [4, 5, 6, 24])

    counts = dict(Counter(x["status"] for x in records))
    blocking = [x["gate"] for x in records if x["status"] == "FAIL"]
    preinstall_critical = {
        "real-elevated-vm-security-audit",
        "interactive-raid-disk-selection-and-ssd1-offline",
        "safe-production-installer-staging",
        "microsoft-winre-after-windows-and-lun-growth-validation",
        "production-postinstall-desired-state-executor",
    }
    preinstall_blockers = [name for name in blocking if name in preinstall_critical]
    postinstall_blockers = [name for name in blocking if name not in preinstall_critical]
    per_requirement = []
    for number in expected:
        # A mapping/coverage test proves only that the requirement is listed;
        # it does not constitute evidence that the product is implemented.
        associated = [r for r in records
                      if number in r["business_requirements"]
                      and r["gate"] != "requirements-1-to-36-traceable"]
        associated_states = {r["status"] for r in associated}
        status = ("FAIL" if "FAIL" in associated_states else
                  "BARE_METAL_ONLY" if "BARE_METAL_ONLY" in associated_states else
                  "PASS" if associated else "NOT_ASSESSED")
        per_requirement.append({
            "id": number, "status": status,
            "evidence_gates": [r["gate"] for r in associated],
        })
    evidence_counts = dict(Counter(item["status"] for item in per_requirement))
    missing_evidence = [item["id"] for item in per_requirement
                        if item["status"] == "NOT_ASSESSED"]
    return {
        "audit_version": 2,
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "status": "NO_GO" if blocking or counts.get("BARE_METAL_ONLY", 0)
        or missing_evidence else "READY",
        "safe_to_start_destructive_asus_setup": False if blocking else None,
        "checks": records,
        "counts": counts,
        "blockers": blocking,
        "preinstall_blockers": preinstall_blockers,
        "postinstall_acceptance_blockers": postinstall_blockers,
        "requirements": per_requirement,
        "requirements_summary": evidence_counts,
        "requirements_without_real_evidence": missing_evidence,
        "vm_audit_status": vm_audit.get("status"),
        "vm_failed": vm_audit.get("failed", []),
        "vm_check_counts": dict(Counter(x["status"] for x in vm_audit.get("checks", []))),
        "owner_prepares_bootable_usb": True,
        "owner_usb_image_creation_is_project_blocker": False,
        "limitation": "Owner-created USB is outside implementation scope; DSC documents and contract passing do not prove configuration is applied or ASUS target disk is correctly selected.",
    }


def main():
    cfg = Config()
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 release_readiness.py GUEST_LIVE_AUDIT.json")
    vm = json.loads(Path(sys.argv[1]).read_text())
    report = review(vm, contract=install_contract_check(cfg),
                    iso=verify_official_iso(cfg), cfg=cfg)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
