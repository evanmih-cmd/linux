import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


class BenchInvariantError(RuntimeError):
    pass


WHY_TCP_IS_FORBIDDEN = (
    "TCP serial is forbidden on this VM bench because it has repeatedly made "
    "VirtualBox launch unreliable: server mode can block launchVMProcess waiting "
    "for a client, and client mode has failed with VERR_TIMEOUT. The supported "
    "COM1 transport is RawFile only."
)

# Hash of the semantically normalized proven AutoYaST profile after removing
# only issue-#3 software surfaces. Storage, boot, networking, credentials,
# users, hostname, and every other installation setting remain frozen.
PROVEN_PROFILE_EXCEPT_SOFTWARE_SHA256 = (
    "5242d2230c572ba89192b92a01e491fbe9b85852d9f869e6ae433b6dfc11f3b4"
)

SOFTWARE_MANAGED_FILE_PATHS = {
    "/etc/udev/rules.d/20-hw1.rules",
    "/etc/xdg/mimeapps.list",
}


def _local_name(name):
    return name.rsplit("}", 1)[-1]


def _software_file_path(file_node):
    for child in list(file_node):
        if _local_name(child.tag) == "file_path":
            return (child.text or "").strip()
    return None


def _normalized_xml_element(element, *, root=False):
    children = []
    for child in list(element):
        child_name = _local_name(child.tag)
        if root and child_name in {"software", "add-on"}:
            continue
        if root and child_name == "files":
            unmanaged = [
                file_node
                for file_node in list(child)
                if not (
                    _local_name(file_node.tag) == "file"
                    and _software_file_path(file_node)
                    in SOFTWARE_MANAGED_FILE_PATHS
                )
            ]
            if not unmanaged:
                continue
            files_copy = ET.Element(child.tag, child.attrib)
            files_copy.text = child.text
            for file_node in unmanaged:
                files_copy.append(file_node)
            children.append(_normalized_xml_element(files_copy))
            continue
        children.append(_normalized_xml_element(child))
    return {
        "tag": _local_name(element.tag),
        "attrs": sorted(
            (_local_name(key), value) for key, value in element.attrib.items()
        ),
        "text": (element.text or "").strip(),
        "children": children,
    }


def profile_except_software_sha256(profile_path):
    root = ET.parse(profile_path).getroot()
    normalized = _normalized_xml_element(root, root=True)
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_proven_profile_except_software(profile_path):
    actual = profile_except_software_sha256(profile_path)
    if actual == PROVEN_PROFILE_EXCEPT_SOFTWARE_SHA256:
        return
    raise BenchInvariantError(
        "proven AutoYaST contract changed outside the top-level <software> "
        "section. Hard fail before build/reset/launch. "
        f"expected={PROVEN_PROFILE_EXCEPT_SOFTWARE_SHA256} actual={actual}. "
        "If a non-software provisioning change is intentionally required, it "
        "must be reviewed as a separate proof change and the golden contract "
        "must be advanced explicitly after that proof."
    )


def validate_source_tree(root):
    root = Path(root)
    violations = []
    for path in sorted(root.glob("*.py")):
        if path.name == "invariants.py":
            continue
        source = path.read_text()
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            raise BenchInvariantError(
                f"VM bench invariant check cannot parse {path}:{exc.lineno}: "
                f"{exc.msg}. Fix the harness before starting a VM cycle."
            ) from exc

        forbidden = re.compile(
            r"\bTCP\b|tcp_serial|serialterm",
            re.IGNORECASE,
        )
        for lineno, line in enumerate(source.splitlines(), 1):
            if forbidden.search(line):
                violations.append(
                    f"{path.name}:{lineno}: forbidden TCP-serial reference: "
                    f"{line.strip()}"
                )

        if "IMachine_setBootOrder" in source:
            violations.append(
                f"{path.name}: BIOS-only IMachine_setBootOrder is forbidden on the UEFI bench"
            )
        for lineno, line in enumerate(source.splitlines(), 1):
            if ".poweroff(" not in line:
                continue
            if path.name == "runner.py" and "control.poweroff()" in line:
                continue
            violations.append(
                f"{path.name}:{lineno}: VM poweroff is allowed only before a new run launch"
            )

        if path.name in ("runner.py", "keyboard.py"):
            secret_input = re.compile(
                r"cfg\.credentials|submit_password|def\s+fill\s*\(",
                re.IGNORECASE,
            )
            for lineno, line in enumerate(source.splitlines(), 1):
                if secret_input.search(line):
                    violations.append(
                        f"{path.name}:{lineno}: forbidden credential-typing path: "
                        f"{line.strip()}"
                    )

    if violations:
        detail = "\n  - ".join(violations)
        raise BenchInvariantError(
            "VM bench invariant violation detected before reset/build/launch.\n"
            f"  - {detail}\n"
            "Required policies: COM1 is RawFile-only; installer secrets are "
            "embedded only by media.py into the generated local OEMDRV or are "
            "entered manually by AutoYaST when absent. runner.py/keyboard.py "
            "must never type credentials."
        )


def validate_profile_storage(profile_path):
    ns = {"y": "http://www.suse.com/1.0/yast2ns"}
    root = ET.parse(profile_path).getroot()
    partitioning = root.find("y:partitioning", ns)
    drives = [] if partitioning is None else partitioning.findall("y:drive", ns)
    errors = []

    def value(node, name):
        child = node.find(f"y:{name}", ns)
        return None if child is None else child.text

    if len(drives) != 2:
        errors.append(f"expected physical target + one LVM drive, got {len(drives)} drives")
    else:
        physical, vg = drives
        if value(physical, "device") != "__TARGET_DEVICE__":
            errors.append(
                "canonical physical target must be __TARGET_DEVICE__ placeholder"
            )
        parts_node = physical.find("y:partitions", ns)
        parts = [] if parts_node is None else parts_node.findall("y:partition", ns)
        if len(parts) != 2:
            errors.append(f"physical target must contain ESP + outer LUKS2, got {len(parts)} partitions")
        else:
            esp, outer = parts
            for key, expected in {
                "mount": "/boot/efi",
                "filesystem": "vfat",
                "format": "true",
                "size": "1GiB",
                "partition_id": "259",
            }.items():
                actual = value(esp, key)
                if actual != expected:
                    errors.append(f"ESP {key}: expected {expected!r}, got {actual!r}")
            for key, expected in {
                "size": "max",
                "lvm_group": "system",
                "crypt_method": "systemd_fde",
                "crypt_pbkdf": "argon2id",
                "crypt_label": "portable-system",
            }.items():
                actual = value(outer, key)
                if actual != expected:
                    errors.append(f"outer LUKS2 {key}: expected {expected!r}, got {actual!r}")

        if value(vg, "device") != "/dev/system":
            errors.append("LVM drive must be /dev/system")
        if value(vg, "type") != "CT_LVM":
            errors.append("LVM drive type must be CT_LVM")
        lvs_node = vg.find("y:partitions", ns)
        lvs = [] if lvs_node is None else lvs_node.findall("y:partition", ns)
        names = [value(lv, "lv_name") for lv in lvs]
        if names != ["root", "home", "swap"]:
            errors.append(f"VG system must contain root/home/swap; got {names}")

    mode = root.find("y:general/y:mode", ns)
    final_halt = None if mode is None else mode.find("y:final_halt", ns)
    if final_halt is not None and (final_halt.text or "").strip().lower() == "true":
        errors.append("AutoYaST final_halt must not be true")

    recovery_paths = [
        node.text for node in root.findall(".//y:ask/y:path", ns)
        if node.text and node.text.startswith("partitioning,")
    ]
    expected_path = "partitioning,0,partitions,1,crypt_key"
    if recovery_paths != [expected_path]:
        errors.append(f"recovery ask path must be {expected_path!r}; got {recovery_paths}")

    if errors:
        detail = "\n  - ".join(errors)
        raise BenchInvariantError(
            "VM bench storage-profile invariant violation before build/reset/launch.\n"
            f"  - {detail}\n"
            "Required topology: GPT -> 1GiB vfat ESP mounted at /boot/efi + "
            "outer systemd_fde LUKS2 -> LVM VG system -> root/home/swap."
        )


def validate_runtime_serial(serial_config, expected_path, phase):
    expected = {
        "enabled": "true",
        "host_mode": "RawFile",
        "io_address": "1016",
        "irq": "4",
    }
    if expected_path is not None:
        expected["path"] = str(expected_path)
    mismatches = {
        key: {"expected": value, "actual": serial_config.get(key)}
        for key, value in expected.items()
        if serial_config.get(key) != value
    }
    if not mismatches:
        return

    raise BenchInvariantError(
        f"VM bench COM1 invariant violation during {phase}. "
        "The VM will not be started.\n"
        f"Reason: {WHY_TCP_IS_FORBIDDEN}\n"
        "Allowed configuration is COM1 RawFile only. "
        f"Mismatch: {json.dumps(mismatches, sort_keys=True)}\n"
        f"Actual COM1: {json.dumps(serial_config, sort_keys=True)}"
    )
