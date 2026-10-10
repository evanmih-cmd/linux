"""Fail-closed boundary between disposable VM access plumbing and release files.

This executes on the controller only. It never changes the guest Windows VM.
Production physical disk selection remains a separate mandatory safety gate.
"""
import json
from pathlib import Path
from xml.etree import ElementTree

from config import Config
from contract import UNATTEND_NS, evaluate_autounattend

# Allowlist is intentionally exhaustive: never copy windows/vm/{harness,payload}
# or the bench cache into a production image/staging directory.
PRODUCTION_FILES = frozenset({"Autounattend.xml", "workstation.winget", "security-hardware.winget", "sandbox-untrusted.wsb", "sandbox-networked.wsb"})
FORBIDDEN_MARKERS = (
    "vboxwindowsadditions",
    "virtualbox",
    "winbench",
    "vmbench",
    "desktopwindows-",
    "programdata\\desktopwindows",
    "elevation-request",
    "register-elevated-task",
    "guest additions",
    "autologon",
    "firstlogoncommands",
    "run-configuration-interactive",
    "credentials.json",
    "schtasks",
    "runas",
)


def verify_production_files(files, *, cfg=None):
    """Validate *actual output bytes*; raise without printing credentials."""
    cfg = cfg or Config()
    if set(files) != PRODUCTION_FILES:
        raise ValueError(
            f"production file allowlist mismatch: expected {sorted(PRODUCTION_FILES)}, "
            f"found {sorted(files)}"
        )

    text_files = {}
    for name, raw in files.items():
        if not isinstance(raw, bytes):
            raise TypeError(f"{name} must be verified from actual file bytes")
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"non-UTF8 production file: {name}") from exc
        low = content.casefold()
        leaked = [marker for marker in FORBIDDEN_MARKERS if marker in low]
        if leaked:
            raise ValueError(f"VM access artifact marker in {name}: {leaked}")
        text_files[name] = content

    answer = text_files["Autounattend.xml"]
    result = evaluate_autounattend(answer)
    if result["status"] != "PASS":
        raise ValueError(f"production answer contract failed: {result['failed']}")

    root = ElementTree.fromstring(answer)
    ns = {"u": UNATTEND_NS}
    accounts = root.findall(
        ".//u:LocalAccount/u:Name", ns
    )
    if any((node.text or "").casefold() == cfg.guest_user.casefold() for node in accounts):
        raise ValueError("VM bench account cannot be shipped in production")

    descriptions = root.findall(".//u:LocalAccount/u:Description", ns)
    if len(descriptions) != 1 or descriptions[0].text != "Owner-controlled local account":
        raise ValueError("production identity must be the owner-controlled local account")
    if root.findall(".//u:LocalAccount/u:Password", ns):
        raise ValueError("password element forbidden on all installation media")

    if cfg.credentials.is_file():
        # Read only to reject accidental reuse. Never report or return its value.
        vm_secret = json.loads(cfg.credentials.read_text()).get("password", "")
        if vm_secret and vm_secret in answer:
            raise ValueError("VM credential appeared in production answer")

    import xml.etree.ElementTree as ET
    # Each profile is a distinct, explicit capability: the offline profile
    # MUST stay disconnected. Networked means NAT connectivity, not filtering.
    for filename, network, startup in (
        ("sandbox-untrusted.wsb", "Disable", r"explorer.exe C:\Incoming"),
        ("sandbox-networked.wsb", "Enable", "resmon.exe"),
    ):
        try:
            sandbox = ET.fromstring(text_files[filename])
        except ET.ParseError as exc:
            raise ValueError(f"invalid Windows Sandbox XML in {filename}") from exc
        expected_sandbox = {
            "vGPU": "Disable", "Networking": network,
            "AudioInput": "Disable", "VideoInput": "Disable",
            "ProtectedClient": "Enable", "PrinterRedirection": "Disable",
            "ClipboardRedirection": "Disable", "MemoryInMB": "4096",
        }
        children = [child.tag for child in sandbox]
        if (sandbox.tag != "Configuration" or len(children) != 10
                or len(set(children)) != len(children)):
            raise ValueError(f"unexpected structure in {filename}")
        values = {
            child.tag: (child.text or "").strip()
            for child in sandbox if child.tag not in {"MappedFolders", "LogonCommand"}
        }
        mapping = sandbox.find("MappedFolders")
        entries = list(mapping) if mapping is not None else []
        folder = entries[0] if len(entries) == 1 else None
        mapped = {
            node.tag: (node.text or "").strip()
            for node in folder
        } if folder is not None else {}
        logon = sandbox.find("LogonCommand")
        command = logon.findtext("Command") if logon is not None else None
        if (values != expected_sandbox
                or folder is None or folder.tag != "MappedFolder"
                or len(list(folder)) != 3
                or mapped != {
                    "HostFolder": r"C:\Sandbox-Inbox",
                    "SandboxFolder": r"C:\Incoming",
                    "ReadOnly": "true",
                } or command != startup
                or logon is None or len(list(logon)) != 1):
            raise ValueError(f"Windows Sandbox profile security contract failed: {filename}")
        canonical_sandbox = (cfg.repo / "windows/configuration" / filename).read_bytes()
        if files[filename] != canonical_sandbox:
            raise ValueError(f"Windows Sandbox differs from reviewed source: {filename}")

    canonical_hardware = (cfg.repo / "windows/configuration/security-hardware.winget").read_bytes()
    if files["security-hardware.winget"] != canonical_hardware:
        raise ValueError("physical ASUS security overlay differs from reviewed source")
    import yaml
    hardware = yaml.safe_load(text_files["security-hardware.winget"])
    resource_locks = hardware.get("resources") or []
    expected_locks = {
        ("HKLM\\SYSTEM\\CurrentControlSet\\Control\\DeviceGuard", "Locked"),
        ("HKLM\\SYSTEM\\CurrentControlSet\\Control\\DeviceGuard\\Scenarios\\HypervisorEnforcedCodeIntegrity", "Locked"),
    }
    def registry_entries(resource):
        """Flatten Microsoft's native v3.3 RegistryList or legacy Registry input."""
        resource_type = resource.get("type")
        props = resource.get("properties") or {}
        if resource_type == "Microsoft.Windows/RegistryList":
            return props.get("registryEntries") or []
        if resource_type == "Microsoft.Windows/Registry":
            return [props]
        return []

    actual_locks = {
        (entry["keyPath"], entry["valueName"])
        for resource in resource_locks
        for entry in registry_entries(resource)
        if entry.get("valueData", {}).get("DWord") == 1
        and entry.get("_exist") is True
        and resource.get("metadata", {}).get("winget", {}).get("securityContext") == "elevated"
    }
    if (len(resource_locks) != 2
            or any(len(registry_entries(r)) != 1 for r in resource_locks)
            or actual_locks != expected_locks):
        raise ValueError("production UEFI lock overlay must contain exactly two approved locks")

    # Common DSC is applied repeatedly. It must never compete with the
    # separate physical-ASUS-only UEFI lock overlay by resetting Locked=0.
    workstation = yaml.safe_load(text_files["workstation.winget"])
    for resource in workstation.get("resources") or []:
        for entry in registry_entries(resource):
            if (entry.get("keyPath"), entry.get("valueName")) in expected_locks:
                raise ValueError("common workstation DSC must not touch ASUS UEFI Lock")

    canonical = cfg.workstation_configuration.read_bytes()
    if files["workstation.winget"] != canonical:
        raise ValueError("production WinGet manifest is not the canonical desired state")

    return {
        "status": "PASS",  # Structural check ONLY: never implies release approval.
        "files": sorted(files),
        "target_selection": "manual-windows-setup-ui",
        "vm_access_artifacts": [],
        "mode": "UNVERIFIED_MANUAL_SELECTION",
        "safe_for_asus_install": False,
        "release_blocker": "Live two-disk installation and SSD1 preservation not yet proved",
    }


def verify_production_directory(directory, *, cfg=None):
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("production staging directory must be a real directory")
    paths = list(directory.iterdir())
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("production staging has an unexpected directory or symlink")
    return verify_production_files(
        {p.name: p.read_bytes() for p in paths},
        cfg=cfg,
    )


def stage_production_files(directory, *, credentials, cfg=None):
    """Block release until the common installer passes two-disk acceptance.

    A structural validation never certifies interactive target selection,
    SSD1 preservation, independent ESP/WinRE, or the physical ASUS.
    """
    raise RuntimeError(
        "Production staging BLOCKED: manual RAID LUN selection and SSD1 "
        "Offline preservation have not passed two-disk acceptance."
    )
