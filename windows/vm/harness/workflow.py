import json
import xml.etree.ElementTree as ET
from pathlib import Path

from answer import build_answer_media, render_autounattend
from config import Config
from contract import BUSINESS_REQUIREMENT_OWNERS, evaluate_autounattend
from media import verify_official_iso
from production_guard import verify_production_files


FORBIDDEN_HARNESS_TEXT = (
    "VBoxManage",
    "keyboard.py",
    "rawserial",
    "sendScancode",
    "AutoYaST",
    "openSUSE",
    "cryptsetup",
)


def _check(name, ok, actual=None, expected=None):
    return {
        "name": name,
        "status": "PASS" if ok else "FAIL",
        "actual": actual,
        "expected": expected,
    }


def _product_signature(xml):
    root = ET.fromstring(xml)
    ns = {"u": "urn:schemas-microsoft-com:unattend"}
    for path in (
        ".//u:ComputerName", ".//u:UserData/u:FullName",
        ".//u:LocalAccount/u:Name", ".//u:LocalAccount/u:DisplayName",
        ".//u:LocalAccount/u:Description",
        ".//u:LocalAccount/u:Password/u:Value",
    ):
        for node in root.findall(path, ns):
            node.text = "__per_install__"
    return ET.tostring(root, encoding="unicode")


def install_contract_check(cfg=None):
    cfg = cfg or Config()
    vm_xml = render_autounattend(
        cfg, {"user": "owner"},
        hostname="SECUREWS", account_display_name="Local owner",
    )
    prod_xml = render_autounattend(
        cfg, {"user": "owner"},
        hostname="SECUREWS",
    )
    vm = evaluate_autounattend(vm_xml)
    production = evaluate_autounattend(prod_xml)
    identical = _product_signature(vm_xml) == _product_signature(prod_xml)
    try:
        guard = verify_production_files({
            "Autounattend.xml": prod_xml.encode("utf-8"),
            **{name: (cfg.repo / "windows/configuration" / name).read_bytes()
               for name in ("workstation.winget", "security-hardware.winget",
                            "sandbox-untrusted.wsb", "sandbox-networked.wsb")},
        }, cfg=cfg)
    except (ValueError, OSError) as exc:
        guard = {"status": "FAIL", "error_type": type(exc).__name__}
    coverage = sorted(map(int, vm["business_requirements"]))
    failed = ["vm:" + key for key in vm.get("failed", [])]
    failed.extend("production:" + key for key in production.get("failed", []))
    if not identical:
        failed.append("different-install-semantics")
    if guard["status"] != "PASS":
        failed.append("production-file-validation")
    if coverage != list(range(1, 37)):
        failed.append("business-requirement-coverage")
    return {
        "status": "FAIL" if failed else "PASS",
        "failed": failed,
        "business_requirements_complete": coverage == list(range(1, 37)),
        "business_requirements": vm["business_requirements"],
        "vm_render": {"status": vm["status"], "failed": vm["failed"],
                      "checks": vm["checks"], "runtime_gates": vm["runtime_gates"],
                      "manual_disk_selection": True, "vm_extension": False},
        "production_render": {
            "status": production["status"], "failed": production["failed"],
            "checks": production["checks"], "runtime_gates": production["runtime_gates"],
            "manual_disk_selection": True, "same_product_xml": identical,
            "safe_for_asus_install": False, "preview_only": True,
            "stage_production_files": "BLOCKED_UNTIL_TWO_DISK_LIVE_ACCEPTANCE",
        },
        "release_status": "BLOCKED",
        "release_reason": "Manual SSD1 Offline and selected LUN not live-proven on two disks",
    }


def static_check(cfg=None):
    cfg = cfg or Config()
    checks = []

    try:
        iso = verify_official_iso(cfg)
        checks.append(
            _check(
                "official-iso-sha256",
                True,
                iso["sha256"],
                cfg.official_iso_sha256,
            )
        )
    except Exception as exc:
        checks.append(
            _check(
                "official-iso-sha256",
                False,
                repr(exc),
                cfg.official_iso_sha256,
            )
        )

    contract = install_contract_check(cfg)
    checks.append(
        _check(
            "autounattend-install-contract",
            contract["status"] == "PASS",
            {
                "failed": contract.get("failed", []),
                "business_requirements_complete": contract.get(
                    "business_requirements_complete"
                ),
            },
            {
                "failed": [],
                "business_requirements_complete": True,
            },
        )
    )

    checks.extend(
        [
            _check(
                "windows-graphics-controller",
                cfg.vm_graphics_controller == "VBoxSVGA",
                cfg.vm_graphics_controller,
                "VBoxSVGA",
            ),
            _check(
                "windows-keyboard-hid",
                cfg.vm_keyboard_hid == "USBKeyboard",
                cfg.vm_keyboard_hid,
                "USBKeyboard",
            ),
            _check(
                "windows-vram",
                cfg.vm_vram_mib >= 128,
                cfg.vm_vram_mib,
                ">=128 MiB",
            ),
            _check(
                "windows-memory",
                cfg.vm_memory_mib >= 4096,
                cfg.vm_memory_mib,
                ">=4096 MiB",
            ),
            _check(
                "windows-vcpus",
                cfg.vm_vcpus >= 2,
                cfg.vm_vcpus,
                ">=2",
            ),
            _check(
                "windows-disk",
                cfg.vm_disk_gib >= 64,
                cfg.vm_disk_gib,
                ">=64 GiB",
            ),
        ]
    )

    required_post_install = (
        cfg.workstation_configuration,
        cfg.configuration_launcher,
        cfg.audit_script,
    )
    for path in required_post_install:
        checks.append(
            _check(
                f"post-install-{path.name}",
                path.is_file() and path.stat().st_size > 0,
                str(path),
                "present and non-empty",
            )
        )

    try:
        media = build_answer_media(cfg)
        verification = media["iso_verification"]
        checks.append(
            _check(
                "autounattend-joliet-media",
                verification.get("status") == "PASS"
                and verification.get("has_joliet") is True
                and verification.get("joliet_names")
                == ["Autounattend.xml"]
                and media.get("xml_contract_status") == "PASS",
                {
                    "verification": verification,
                    "xml_contract_status": media.get(
                        "xml_contract_status"
                    ),
                },
                {
                    "has_joliet": True,
                    "joliet_names": ["Autounattend.xml"],
                    "xml_contract_status": "PASS",
                },
            )
        )
    except Exception as exc:
        checks.append(
            _check(
                "autounattend-joliet-media",
                False,
                repr(exc),
                "valid Joliet DVD with exact Autounattend.xml",
            )
        )

    provenance = cfg.repo / "windows/vm/ISO_PROVENANCE.md"
    provenance_text = provenance.read_text() if provenance.exists() else ""
    checks.append(
        _check(
            "iso-provenance-recorded",
            cfg.official_iso_sha256.upper() in provenance_text.upper(),
            str(provenance),
            cfg.official_iso_sha256,
        )
    )

    harness_dir = Path(__file__).resolve().parent
    source_errors = []
    for path in sorted(harness_dir.glob("*.py")):
        text = path.read_text()
        try:
            compile(text, str(path), "exec")
        except SyntaxError as exc:
            source_errors.append(f"{path.name}: syntax: {exc}")
        if path.name.startswith("test_"):
            continue
        for forbidden in FORBIDDEN_HARNESS_TEXT:
            if forbidden in text and path.name != "workflow.py":
                source_errors.append(
                    f"{path.name}: forbidden legacy transport/text {forbidden!r}"
                )
    checks.append(
        _check(
            "windows-harness-source",
            not source_errors,
            source_errors,
            "compiles; no legacy keyboard/VBoxManage transport; bounded SOAP boot Enter only",
        )
    )

    cred_path = cfg.credentials.resolve()
    repo = cfg.repo.resolve()
    checks.append(
        _check(
            "vm-credentials-outside-git",
            repo not in cred_path.parents,
            str(cred_path),
            "outside repository",
        )
    )

    failed = [x["name"] for x in checks if x["status"] == "FAIL"]
    return {
        "status": "FAIL" if failed else "PASS",
        "failed": failed,
        "checks": checks,
    }


def print_check(cfg=None):
    result = static_check(cfg)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1
