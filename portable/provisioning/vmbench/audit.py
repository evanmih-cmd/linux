import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from config import Config
from keyboard import Keyboard
from machine import unc
from media import load_credentials
from rawserial import RawSerialMonitor
from vbox import VBox


TARGET_BY_ID = (
    "/dev/disk/by-id/"
    "ata-PORTABLE_WORKSTATION_SSD_PORTABLETARGET000001"
)
ESP_BYTES = 1024 ** 3
ESP_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"

FORBIDDEN_PROBE_FRAGMENTS = (
    "reboot", "poweroff", "shutdown", "halt", " mount ", "umount",
    "mkfs", "parted", "sgdisk", "fdisk", "wipefs", " dd ",
    "luksaddkey", "luksremovekey", "luksformat",
    "cryptsetup open", "cryptsetup close",
    "lvcreate", "lvremove", "vgcreate", "vgremove", "pvcreate",
    "snapper create", "snapper delete", "snapper rollback",
    "btrfs subvolume create", "btrfs subvolume delete",
    "systemctl enable", "systemctl disable", "systemctl start",
    "systemctl stop", "systemctl restart",
    "zypper ", "rpm -i", "rpm -u",
)


class AuditFailure(RuntimeError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for chunk in iter(lambda: src.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def autoyast_installed_asset_sha256(relative_path, cfg=None):
    """Hash bytes after AutoYaST's trailing-newline normalization."""
    cfg = cfg or Config()
    data = (
        cfg.repo / "portable/provisioning/assets" / relative_path
    ).read_bytes().rstrip(b"\n")
    return hashlib.sha256(data).hexdigest()


def expected_managed_file_hash(relative_path, cfg=None):
    cfg = cfg or Config()
    data = (cfg.repo / "portable/provisioning/assets" / relative_path).read_bytes().rstrip(b"\n")
    return hashlib.sha256(data).hexdigest()


def probe_commands():
    return [
        ("uid", "id -u"),
        ("hostname", "hostname"),
        ("etc_hostname", "cat /etc/hostname"),
        ("os_release", "cat /etc/os-release"),
        ("kernel", "uname -r"),
        ("target_device", f"readlink -f {TARGET_BY_ID}"),
        (
            "lsblk",
            "lsblk -b -J -o NAME,PATH,TYPE,SIZE,FSTYPE,FSVER,"
            "LABEL,UUID,PARTUUID,PARTTYPE,MOUNTPOINTS",
        ),
        ("findmnt", "findmnt -n -P -o TARGET,SOURCE,FSTYPE,OPTIONS"),
        ("pvs", "pvs --reportformat json -o pv_name,vg_name"),
        ("vgs", "vgs --reportformat json -o vg_name,vg_size,vg_free"),
        ("lvs", "lvs --reportformat json -o vg_name,lv_name,lv_size"),
        (
            "swapon",
            "swapon --show --bytes --noheadings --output NAME,SIZE,TYPE",
        ),
        ("fstab", "cat /etc/fstab"),
        ("crypttab", "cat /etc/crypttab"),
        (
            "luks_json",
            f"cryptsetup luksDump --dump-json-metadata {TARGET_BY_ID}-part2",
        ),
        ("btrfs_subvols", "btrfs subvolume list -a /"),
        ("btrfs_default", "btrfs subvolume get-default /"),
        ("snapper_configs", "snapper list-configs"),
        ("snapper_root", "snapper --csvout -c root list"),
        (
            "boot_files",
            "find /boot/efi -maxdepth 5 -type f -printf '%P\\n' | sort",
        ),
        (
            "bls",
            "for f in /boot/efi/loader/entries/*.conf; do "
            "echo ===$f===; cat $f; done",
        ),
        (
            "bls_missing",
            "for f in /boot/efi/loader/entries/*.conf; do "
            "awk '$1==\"linux\"||$1==\"initrd\"{print $2}' $f; done | "
            "while read p; do test -e /boot/efi$p || echo $p; done",
        ),
        (
            "nm_files",
            "find /etc/NetworkManager -maxdepth 2 -type f "
            "-printf '%P\\n' | sort",
        ),
        ("nm_effective", "NetworkManager --print-config"),
        ("nm_service", "systemctl is-active NetworkManager"),
        ("failed_units", "systemctl --failed --no-legend --plain"),
        ("system_state", "systemctl is-system-running"),
        ("desktop_user", "id portable"),
        (
            "root_account",
            "getent passwd root; passwd -S root 2>&1 || true",
        ),
        (
            "sddm_pam",
            "for f in /etc/pam.d/sddm /usr/lib/pam.d/sddm "
            "/etc/pam.d/common-auth /etc/pam.d/common-account "
            "/usr/lib/pam.d/common-auth /usr/lib/pam.d/common-account; do "
            "test -e $f || continue; echo ===$f===; cat $f; done",
        ),
        (
            "sddm_config",
            "for d in /etc/sddm.conf /etc/sddm.conf.d "
            "/usr/lib/sddm/sddm.conf.d; do "
            "if test -f $d; then echo ===$d===; cat $d; "
            "elif test -d $d; then for f in $d/*.conf; do "
            "test -e $f || continue; echo ===$f===; cat $f; done; fi; done",
        ),
        (
            "sddm_journal",
            "journalctl -b --no-pager -n 300 "
            "-u display-manager.service "
            "-u display-manager-legacy.service "
            "-u sddm.service 2>&1 || true",
        ),
        (
            "login_sessions",
            "loginctl list-sessions --no-legend; "
            "for s in $(loginctl list-sessions --no-legend | awk '{print $1}'); do "
            "echo ===$s===; loginctl show-session $s "
            "-p Id -p Name -p User -p State -p Type -p Class -p Service "
            "-p Desktop -p Seat -p TTY -p VTNr -p Leader; done",
        ),
        (
            "plasma_processes",
            "ps -u portable -o pid,ppid,stat,comm,args",
        ),
        (
            "logind_status",
            "systemctl status systemd-logind --no-pager -l",
        ),
        (
            "logind_config",
            "grep -RHE '^[[:space:]]*(HandlePowerKey|HandlePowerKeyLongPress|"
            "PowerKeyIgnoreInhibited|LidSwitchIgnoreInhibited)=' "
            "/etc/systemd/logind.conf /etc/systemd/logind.conf.d "
            "/usr/lib/systemd/logind.conf.d 2>/dev/null || true",
        ),
        (
            "logind_properties",
            "for p in HandlePowerKey HandlePowerKeyLongPress "
            "PowerKeyIgnoreInhibited; do printf \"$p=\"; "
            "busctl get-property org.freedesktop.login1 "
            "/org/freedesktop/login1 org.freedesktop.login1.Manager "
            "$p 2>&1 || true; done",
        ),
        (
            "inhibitors",
            "timeout 8 systemd-inhibit --list --no-pager || true",
        ),
        (
            "desktop_journal",
            "journalctl -b _UID=$(id -u portable) --no-pager -n 300",
        ),
        ("packages", "rpm -q sdbootutil snapper NetworkManager lvm2"),
        (
            "software_packages",
            "rpm -q MozillaFirefox google-chrome-stable NetworkManager "
            "plasma6-nm wpa_supplicant firewalld transactional-update "
            "zypp-boot-plugin sdbootutil-tukit",
        ),
        (
            "software_patterns",
            "rpm -q patterns-base-base patterns-base-hardware "
            "patterns-kde-kde_plasma",
        ),
        (
            "software_forbidden",
            "for p in patterns-kde-kde patterns-base-enhanced_base "
            "openssh-server fwupd flatpak; do "
            "rpm -q \"$p\" >/dev/null 2>&1 && echo \"$p\"; done; true",
        ),
        (
            "package_closure",
            "rpm -qa --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\\n' | sort",
        ),
        (
            "software_files",
            "sha256sum /etc/udev/rules.d/20-hw1.rules "
            "/etc/xdg/mimeapps.list",
        ),
        (
            "firewalld_state",
            "printf 'enabled='; systemctl is-enabled firewalld; "
            "printf 'active='; systemctl is-active firewalld",
        ),
        ("pin_file_absent", "test ! -e /etc/desktop-linux-tpm2-pin"),
    ]


def validate_probe_commands(commands=None):
    commands = commands or probe_commands()
    errors = []
    for name, command in commands:
        padded = f" {command.lower()} "
        for fragment in FORBIDDEN_PROBE_FRAGMENTS:
            if fragment in padded:
                errors.append(f"{name}: forbidden fragment {fragment!r}")
    if errors:
        raise AuditFailure(
            "unsafe audit probe:\n  - " + "\n  - ".join(errors)
        )
    return commands


def build_probe_script(token):
    lines = [
        "#!/bin/bash",
        "set +e",
        "export SYSTEMD_PAGER=cat PAGER=cat SYSTEMD_COLORS=0",
        "exec >/dev/ttyS0 2>&1",
        f"TOKEN={shlex.quote(token)}",
        'echo "__AUDIT_BEGIN__"$TOKEN',
        "section() {",
        '  name="$1"',
        '  cmd="$2"',
        '  echo "__AUDIT_SECTION__"$TOKEN"__"$name',
        '  /bin/bash -c "$cmd"',
        "  rc=$?",
        '  echo "__AUDIT_RC__"$TOKEN"__"$name"__"$rc',
        "}",
    ]
    for name, command in validate_probe_commands():
        lines.append(
            f"section {shlex.quote(name)} {shlex.quote(command)}"
        )
    lines.append('echo "__AUDIT_DONE__"$TOKEN')
    return "\n".join(lines) + "\n"


def build_audit_iso(cfg, run_dir, token):
    media_root = Path(run_dir) / "audit-media"
    media_root.mkdir()
    script = media_root / "audit.sh"
    script.write_text(build_probe_script(token))
    script.chmod(0o755)

    iso = Path(run_dir) / "audit.iso"
    xroot = cfg.cache / "tools/rootless/xorriso"
    xorriso = xroot / "usr/bin/xorriso"
    libdir = xroot / "usr/lib/x86_64-linux-gnu"
    if not xorriso.exists():
        raise AuditFailure(f"xorriso is missing: {xorriso}")

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(libdir)
    proc = subprocess.run(
        [
            str(xorriso), "-as", "mkisofs", "-quiet",
            "-V", "DLAUDIT", "-o", str(iso), str(media_root),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise AuditFailure(
            "xorriso failed: " + (proc.stderr or proc.stdout).strip()
        )
    return iso


def hot_swap_audit_iso(box, iso):
    medium = box._vals(
        "IVirtualBox_openMedium",
        [
            ("_this", box.handle),
            ("location", unc(iso)),
            ("deviceType", "DVD"),
            ("accessMode", "ReadOnly"),
            ("forceNewUuid", "false"),
        ],
    )[0]
    session = box.lock("Shared")
    try:
        machine = box.session_machine(session)
        box._vals(
            "IMachine_mountMedium",
            [
                ("_this", machine),
                ("name", "SATA"),
                ("controllerPort", "3"),
                ("device", "0"),
                ("medium", medium),
                ("force", "true"),
            ],
        )
    finally:
        box.unlock(session)


def audit_launcher(token):
    mountpoint = f"/run/dla-{token}"
    return (
        f"mkdir -p {mountpoint};"
        f"mount -o ro /dev/disk/by-label/DLAUDIT {mountpoint};"
        f"bash {mountpoint}/audit.sh;"
        f"umount {mountpoint};"
        f"rmdir {mountpoint}"
    )

def local_serial_path(raw_path):
    text = raw_path.replace("\\", "/")
    prefix = "//wsl.localhost/runner02/"
    if not text.lower().startswith(prefix):
        raise AuditFailure(
            f"COM1 RawFile is not runner02-accessible: {raw_path!r}"
        )
    return Path("/" + text[len(prefix):])


def parse_probe(text, token):
    begin = f"__AUDIT_BEGIN__{token}"
    done = f"__AUDIT_DONE__{token}"
    start = text.rfind(begin)
    end = text.find(done, start + len(begin)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise AuditFailure(
            "complete audit probe markers were not captured on COM1"
        )

    payload = text[start + len(begin):end]
    pattern = re.compile(
        rf"__AUDIT_SECTION__{re.escape(token)}__([a-z0-9_]+)\s*\n"
    )
    matches = list(pattern.finditer(payload))
    sections = {}
    for index, match in enumerate(matches):
        name = match.group(1)
        block_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(payload)
        )
        block = payload[match.end():block_end]
        rc_pattern = re.compile(
            rf"__AUDIT_RC__{re.escape(token)}__"
            rf"{re.escape(name)}__([0-9]+)"
        )
        rc_matches = list(rc_pattern.finditer(block))
        if not rc_matches:
            raise AuditFailure(
                f"missing return-code marker for section {name}"
            )
        rc_match = rc_matches[-1]
        sections[name] = {
            "rc": int(rc_match.group(1)),
            "output": block[:rc_match.start()].strip("\n"),
        }

    expected = {name for name, _ in probe_commands()}
    missing = sorted(expected - set(sections))
    if missing:
        raise AuditFailure(
            f"audit probe omitted sections: {', '.join(missing)}"
        )
    return sections


def parse_pairs(text):
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        row = {}
        for field in shlex.split(line):
            key, sep, value = field.partition("=")
            if sep:
                row[key] = value
        if row:
            rows.append(row)
    return rows


def parse_lvm_json(text, key):
    data = json.loads(text)
    reports = data.get("report", [])
    if len(reports) != 1 or key not in reports[0]:
        raise AuditFailure(f"invalid LVM JSON for {key}")
    return reports[0][key]


def flatten_lsblk(devices):
    out = []

    def visit(node):
        out.append(node)
        for child in node.get("children") or []:
            visit(child)

    for device in devices:
        visit(device)
    return out


def table_rows(text):
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(line.split())
    return rows


def result_check(
    name, ok, actual=None, expected=None, warning=False
):
    return {
        "name": name,
        "status": (
            "PASS" if ok else ("WARN" if warning else "FAIL")
        ),
        "actual": actual,
        "expected": expected,
    }


def evaluate(sections):
    checks = []
    facts = {}
    out = lambda name: sections[name]["output"].strip()

    checks.append(result_check(
        "root-shell",
        sections["uid"]["rc"] == 0 and out("uid") == "0",
        out("uid"),
        "0",
    ))

    hostname = out("hostname")
    etc_hostname = out("etc_hostname")
    facts["hostname"] = hostname
    checks.append(result_check(
        "hostname",
        hostname == "portable" and etc_hostname == "portable",
        {"runtime": hostname, "etc": etc_hostname},
        "portable",
    ))

    os_release = {}
    for line in out("os_release").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            os_release[key] = value.strip().strip('"')
    facts["os_release"] = os_release
    checks.append(result_check(
        "tumbleweed-release",
        os_release.get("ID") == "opensuse-tumbleweed",
        os_release.get("ID"),
        "opensuse-tumbleweed",
    ))

    target = (
        out("target_device")
        if sections["target_device"]["rc"] == 0
        else ""
    )
    facts["target_device"] = target
    checks.append(result_check(
        "portable-target-by-id",
        target.startswith("/dev/"),
        target,
        TARGET_BY_ID,
    ))

    try:
        devices = json.loads(out("lsblk")).get("blockdevices", [])
        flat = flatten_lsblk(devices)
        lsblk_error = None
    except Exception as exc:
        devices, flat = [], []
        lsblk_error = repr(exc)
    checks.append(result_check(
        "lsblk-json",
        lsblk_error is None,
        lsblk_error,
        "valid JSON",
    ))

    disk = next(
        (
            item for item in devices
            if item.get("path") == target
            and item.get("type") == "disk"
        ),
        None,
    )
    checks.append(result_check(
        "target-disk",
        disk is not None,
        target,
        "portable target disk",
    ))
    partitions = [
        item for item in ((disk or {}).get("children") or [])
        if item.get("type") == "part"
    ]
    checks.append(result_check(
        "target-partition-count",
        len(partitions) == 2,
        len(partitions),
        2,
    ))

    esp = partitions[0] if len(partitions) > 0 else {}
    outer = partitions[1] if len(partitions) > 1 else {}
    esp_size = int(esp.get("size") or 0)
    checks.extend([
        result_check(
            "esp-size",
            abs(esp_size - ESP_BYTES) <= 4 * 1024 ** 2,
            esp_size,
            "1 GiB (+/- 4 MiB)",
        ),
        result_check(
            "esp-type",
            str(esp.get("parttype") or "").lower() == ESP_GUID,
            esp.get("parttype"),
            ESP_GUID,
        ),
        result_check(
            "esp-filesystem",
            esp.get("fstype") == "vfat",
            esp.get("fstype"),
            "vfat",
        ),
        result_check(
            "esp-mounted",
            "/boot/efi" in (esp.get("mountpoints") or []),
            esp.get("mountpoints"),
            ["/boot/efi"],
        ),
        result_check(
            "outer-luks2",
            outer.get("fstype") == "crypto_LUKS"
            and str(outer.get("fsver")) == "2",
            {
                "fstype": outer.get("fstype"),
                "fsver": outer.get("fsver"),
            },
            {"fstype": "crypto_LUKS", "fsver": "2"},
        ),
    ])

    foreign_uses = []
    for item in devices:
        if item.get("type") != "disk" or item.get("path") == target:
            continue
        for node in flatten_lsblk([item]):
            mounts = [
                value for value in (node.get("mountpoints") or [])
                if value
            ]
            if mounts or node.get("type") in ("crypt", "lvm"):
                foreign_uses.append({
                    "path": node.get("path"),
                    "type": node.get("type"),
                    "mountpoints": mounts,
                })
    checks.append(result_check(
        "internal-disks-unused",
        not foreign_uses,
        foreign_uses,
        [],
    ))

    try:
        pvs = parse_lvm_json(out("pvs"), "pv")
        vgs = parse_lvm_json(out("vgs"), "vg")
        lvs = parse_lvm_json(out("lvs"), "lv")
        lvm_error = None
    except Exception as exc:
        pvs, vgs, lvs = [], [], []
        lvm_error = repr(exc)
    checks.append(result_check(
        "lvm-json",
        lvm_error is None,
        lvm_error,
        "valid LVM JSON",
    ))
    vg_names = sorted({
        item.get("vg_name", "").strip()
        for item in vgs if item.get("vg_name", "").strip()
    })
    lv_names = sorted(
        item.get("lv_name", "").strip()
        for item in lvs
        if item.get("vg_name", "").strip() == "system"
    )
    system_pvs = [
        item for item in pvs
        if item.get("vg_name", "").strip() == "system"
    ]
    checks.extend([
        result_check("vg-system", vg_names == ["system"], vg_names, ["system"]),
        result_check(
            "lv-layout",
            lv_names == ["home", "root", "swap"],
            lv_names,
            ["home", "root", "swap"],
        ),
        result_check(
            "single-system-pv",
            len(system_pvs) == 1,
            system_pvs,
            "one PV",
        ),
    ])

    mounts = parse_pairs(out("findmnt"))
    by_target = {
        item.get("TARGET"): item for item in mounts
        if item.get("TARGET")
    }
    root_mount = by_target.get("/") or {}
    home_mount = by_target.get("/home") or {}
    esp_mount = by_target.get("/boot/efi") or {}
    checks.extend([
        result_check(
            "root-btrfs",
            root_mount.get("FSTYPE") == "btrfs"
            and "system-root" in root_mount.get("SOURCE", ""),
            root_mount,
            "system-root btrfs",
        ),
        result_check(
            "home-xfs",
            home_mount.get("FSTYPE") == "xfs"
            and "system-home" in home_mount.get("SOURCE", ""),
            home_mount,
            "system-home xfs",
        ),
        result_check(
            "esp-live-mount",
            esp_mount.get("FSTYPE") == "vfat",
            esp_mount,
            "vfat at /boot/efi",
        ),
    ])
    checks.append(result_check(
        "swap-active",
        sections["swapon"]["rc"] == 0 and bool(out("swapon")),
        out("swapon"),
        "active swap LV",
    ))


    fstab = table_rows(out("fstab"))
    by_mount = {
        row[1]: row for row in fstab
        if len(row) >= 3
    }
    checks.extend([
        result_check(
            "fstab-root",
            len(by_mount.get("/", [])) >= 3
            and by_mount["/"][2] == "btrfs",
            by_mount.get("/"),
            "btrfs",
        ),
        result_check(
            "fstab-home",
            len(by_mount.get("/home", [])) >= 3
            and by_mount["/home"][2] == "xfs",
            by_mount.get("/home"),
            "xfs",
        ),
        result_check(
            "fstab-esp",
            len(by_mount.get("/boot/efi", [])) >= 3
            and by_mount["/boot/efi"][2] == "vfat",
            by_mount.get("/boot/efi"),
            "vfat",
        ),
        result_check(
            "fstab-swap",
            any(
                len(row) >= 3 and row[2] == "swap"
                for row in fstab
            ),
            [row for row in fstab if len(row) >= 3 and row[2] == "swap"],
            "swap entry",
        ),
    ])

    crypttab = table_rows(out("crypttab"))
    crypt_options = set()
    if len(crypttab) == 1 and len(crypttab[0]) >= 4:
        crypt_options = set(crypttab[0][3].split(","))
    required_options = {
        "tpm2-device=auto",
        "x-initrd.attach",
        "tpm2-measure-pcr=yes",
    }
    checks.extend([
        result_check(
            "crypttab-single-entry",
            len(crypttab) == 1,
            len(crypttab),
            1,
        ),
        result_check(
            "crypttab-options",
            required_options.issubset(crypt_options),
            sorted(crypt_options),
            sorted(required_options),
        ),
    ])

    try:
        luks = json.loads(out("luks_json"))
        keyslots = luks.get("keyslots", {})
        tokens = luks.get("tokens", {})
        tpm_tokens = [
            token for token in tokens.values()
            if token.get("type") == "systemd-tpm2"
        ]
        pin_tokens = [
            token for token in tpm_tokens
            if token.get("tpm2-pin") in (True, "true", 1)
        ]
        luks_error = None
    except Exception as exc:
        keyslots, tpm_tokens, pin_tokens = {}, [], []
        luks_error = repr(exc)
    checks.extend([
        result_check(
            "luks-json",
            luks_error is None,
            luks_error,
            "valid LUKS2 metadata",
        ),
        result_check(
            "luks-keyslots",
            len(keyslots) >= 2,
            sorted(keyslots),
            "at least recovery + TPM keyslots",
        ),
        result_check(
            "tpm2-token-metadata",
            len(tpm_tokens) == 1,
            len(tpm_tokens),
            1,
        ),
        result_check(
            "tpm2-pin-metadata",
            len(pin_tokens) == 1,
            len(pin_tokens),
            1,
        ),
    ])

    subvols = out("btrfs_subvols")
    default_subvol = out("btrfs_default")
    checks.extend([
        result_check(
            "btrfs-snapshots-subvolume",
            ".snapshots" in subvols,
            ".snapshots" in subvols,
            True,
        ),
        result_check(
            "btrfs-default-subvolume",
            sections["btrfs_default"]["rc"] == 0
            and "ID" in default_subvol,
            default_subvol,
            "valid default subvolume",
        ),
    ])

    snapper_configs = out("snapper_configs")
    snapper_root = out("snapper_root")
    snapshot_lines = [
        line for line in snapper_root.splitlines()
        if line.strip()
    ]
    checks.extend([
        result_check(
            "snapper-root-config",
            sections["snapper_configs"]["rc"] == 0
            and re.search(r"\broot\b", snapper_configs) is not None,
            snapper_configs,
            "root config",
        ),
        result_check(
            "snapper-list",
            sections["snapper_root"]["rc"] == 0
            and len(snapshot_lines) >= 2,
            len(snapshot_lines),
            "snapshot rows",
        ),
        result_check(
            "snapper-install-snapshot",
            "installation" in snapper_root.lower(),
            "installation" in snapper_root.lower(),
            True,
        ),
    ])

    boot_files = set(
        line.strip()
        for line in out("boot_files").splitlines()
        if line.strip()
    )
    bls_files = sorted(
        item for item in boot_files
        if item.startswith("loader/entries/")
        and item.endswith(".conf")
    )
    checks.extend([
        result_check(
            "removable-fallback",
            "EFI/BOOT/BOOTX64.EFI" in boot_files,
            "EFI/BOOT/BOOTX64.EFI" in boot_files,
            True,
        ),
        result_check(
            "bls-entry-files",
            bool(bls_files),
            bls_files,
            "at least one BLS entry",
        ),
        result_check(
            "bls-references-exist",
            sections["bls_missing"]["rc"] == 0
            and not out("bls_missing"),
            out("bls_missing"),
            "",
        ),
        result_check(
            "pcrlock-asset",
            "EFI/systemd/pcrlock.json" in boot_files,
            "EFI/systemd/pcrlock.json" in boot_files,
            True,
        ),
        result_check(
            "measure-pcr-prediction",
            "EFI/systemd/measure-pcr-prediction" in boot_files,
            "EFI/systemd/measure-pcr-prediction" in boot_files,
            True,
        ),
    ])

    nm_files = out("nm_files").splitlines()
    nm_effective = out("nm_effective")
    checks.extend([
        result_check(
            "networkmanager-service",
            out("nm_service") == "active",
            out("nm_service"),
            "active",
        ),
        result_check(
            "networkmanager-config",
            sections["nm_effective"]["rc"] == 0
            and "[main]" in nm_effective,
            {
                "etc_files": nm_files[:20],
                "effective_has_main": "[main]" in nm_effective,
            },
            "effective NetworkManager configuration",
        ),
    ])

    ansi_csi = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    failed = [
        clean
        for line in out("failed_units").splitlines()
        if (clean := ansi_csi.sub("", line).strip())
    ]
    kdump_only = bool(failed) and all(
        "kdump.service" in line or "kdump-early.service" in line
        for line in failed
    )
    checks.append(result_check(
        "failed-units",
        not failed,
        failed,
        [],
        warning=kdump_only,
    ))
    system_state = out("system_state")
    state_ok = system_state == "running"
    state_warn = system_state == "degraded" and kdump_only
    checks.append(result_check(
        "system-state",
        state_ok,
        system_state,
        "running",
        warning=state_warn,
    ))

    checks.append(result_check(
        "required-packages",
        sections["packages"]["rc"] == 0,
        out("packages").splitlines(),
        ["sdbootutil", "snapper", "NetworkManager", "lvm2"],
    ))
    checks.append(result_check(
        "software-baseline-packages",
        sections["software_packages"]["rc"] == 0,
        out("software_packages").splitlines(),
        [
            "MozillaFirefox",
            "google-chrome-stable",
            "NetworkManager",
            "plasma6-nm",
            "wpa_supplicant",
            "firewalld",
            "transactional-update",
            "zypp-boot-plugin",
            "sdbootutil-tukit",
        ],
    ))
    checks.append(result_check(
        "software-baseline-patterns",
        sections["software_patterns"]["rc"] == 0,
        out("software_patterns").splitlines(),
        [
            "patterns-base-base",
            "patterns-base-hardware",
            "patterns-kde-kde_plasma",
        ],
    ))
    forbidden_software = out("software_forbidden").splitlines()
    checks.append(result_check(
        "software-forbidden-baseline-absent",
        sections["software_forbidden"]["rc"] == 0
        and not forbidden_software,
        forbidden_software,
        [],
    ))
    facts["package_closure"] = [
        line for line in out("package_closure").splitlines() if line.strip()
    ]
    checks.append(result_check(
        "package-closure-captured",
        sections["package_closure"]["rc"] == 0
        and bool(facts["package_closure"]),
        len(facts["package_closure"]),
        "non-empty installed RPM closure",
    ))
    software_hashes = {
        line for line in out("software_files").splitlines() if line.strip()
    }
    required_software_hashes = {
        f"{expected_managed_file_hash('20-hw1.rules')}  /etc/udev/rules.d/20-hw1.rules",
        f"{expected_managed_file_hash('mimeapps.list')}  /etc/xdg/mimeapps.list",
    }
    checks.append(result_check(
        "software-managed-files",
        sections["software_files"]["rc"] == 0
        and software_hashes == required_software_hashes,
        sorted(software_hashes),
        sorted(required_software_hashes),
    ))
    checks.append(result_check(
        "firewalld-enabled-active",
        sections["firewalld_state"]["rc"] == 0
        and "enabled=enabled" in out("firewalld_state")
        and "active=active" in out("firewalld_state"),
        out("firewalld_state"),
        "enabled=enabled / active=active",
    ))
    checks.append(result_check(
        "installer-pin-file-absent",
        sections["pin_file_absent"]["rc"] == 0,
        "absent" if sections["pin_file_absent"]["rc"] == 0 else "present",
        "absent",
    ))

    return {"checks": checks, "facts": facts}


def summarize(evaluation):
    failures = [
        item["name"] for item in evaluation["checks"]
        if item["status"] == "FAIL"
    ]
    warnings = [
        item["name"] for item in evaluation["checks"]
        if item["status"] == "WARN"
    ]
    return {
        "status": "FAIL" if failures else "PASS",
        "failed": failures,
        "warnings": warnings,
        "check_count": len(evaluation["checks"]),
        "pass_count": sum(
            item["status"] == "PASS"
            for item in evaluation["checks"]
        ),
    }


def persistent_boot_state(data):
    out = {}
    for name, value in data.items():
        if name == "BootOrder":
            out[name] = value
            continue
        if len(name) == 8 and name.startswith("Boot"):
            suffix = name[4:]
            if all(ch in "0123456789abcdefABCDEF" for ch in suffix):
                out[name] = value
    return out


class InstalledAudit:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config()
        self.root = self.cfg.bench / "audits"
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.dir = self.root / stamp
        suffix = 0
        while self.dir.exists():
            suffix += 1
            self.dir = self.root / f"{stamp}-{suffix}"
        self.dir.mkdir()
        self.events = open(
            self.dir / "events.jsonl", "a", buffering=1
        )

    def event(self, name, **fields):
        record = {"event": name, "ts": time.time(), **fields}
        self.events.write(
            json.dumps(record, sort_keys=True) + "\n"
        )

    def result(self, status, **fields):
        data = {
            "status": status,
            "run": str(self.dir),
            **fields,
        }
        (self.dir / "result.json").write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        return data

    def send_line(self, keyboard, line):
        keyboard.text_fast(line)
        keyboard.enter()

    def run(self):
        box = VBox(self.cfg)
        keyboard = None
        try:
            if box.state() != "Running":
                raise AuditFailure(
                    "post-boot audit requires an already Running VM; "
                    f"got {box.state()}"
                )

            serial = box.serial_config()
            if (
                serial.get("enabled") != "true"
                or serial.get("host_mode") != "RawFile"
            ):
                raise AuditFailure(
                    f"COM1 must already be RawFile: {serial}"
                )
            serial_path = local_serial_path(
                serial.get("path") or ""
            )
            monitor = RawSerialMonitor(
                serial_path, self.dir, self.event
            )
            mark = monitor.mark()

            attachments = box.attachments()
            (self.dir / "attachments.json").write_text(
                json.dumps(
                    attachments, indent=2, sort_keys=True
                ) + "\n"
            )

            nvram_before = box.nvram_boot_variables()
            (self.dir / "nvram.before.json").write_text(
                json.dumps(
                    nvram_before, indent=2, sort_keys=True
                ) + "\n"
            )
            guard_before = sha256(self.cfg.guard)
            self.event(
                "preflight-pass",
                vm_state="Running",
                serial=str(serial_path),
                guard_sha256=guard_before,
            )

            token = uuid.uuid4().hex[:12]
            audit_iso = build_audit_iso(
                self.cfg, self.dir, token
            )
            hot_swap_audit_iso(box, audit_iso)
            self.event(
                "audit-media-ready",
                iso=str(audit_iso),
                sha256=sha256(audit_iso),
            )

            keyboard = Keyboard(box)
            ready = "auditready" + token
            credentials = load_credentials(self.cfg)
            root_password = credentials.get("root")
            if not root_password:
                raise AuditFailure(
                    "post-boot audit requires the VM root credential"
                )

            # The installed system boots into the graphical target. Switch to
            # a real text VT and log in there before sending the tiny audit
            # launcher. This keeps the transport inside the harness and avoids
            # relying on whatever GUI currently owns keyboard focus.
            keyboard.ctrl_alt_fn(6)
            time.sleep(0.8)
            keyboard.text("root")
            keyboard.enter()
            time.sleep(0.8)
            keyboard.text(root_password)
            keyboard.enter()
            time.sleep(1.2)
            keyboard.text(f"echo {ready}>/dev/ttyS0")
            keyboard.enter()
            monitor.wait_any(
                ready, timeout=10, new_since=mark
            )
            self.event("root-shell-observed", transport="tty6-login")

            probe_mark = monitor.mark()
            self.send_line(keyboard, audit_launcher(token))
            monitor.wait_any(
                f"__AUDIT_DONE__{token}",
                timeout=90,
                new_since=probe_mark,
            )

            captured = monitor._bytes()[probe_mark:]
            (self.dir / "probe-output.log").write_bytes(
                captured
            )
            keyboard.text("exit")
            keyboard.enter()
            time.sleep(0.4)
            self.event("root-shell-closed", transport="tty6-login")
            text = captured.decode(
                "utf-8", "replace"
            ).replace("\r", "\n")
            sections = parse_probe(text, token)
            (self.dir / "sections.json").write_text(
                json.dumps(
                    sections, indent=2, sort_keys=True
                ) + "\n"
            )

            evaluation = evaluate(sections)
            summary = summarize(evaluation)
            (self.dir / "checks.json").write_text(
                json.dumps(
                    evaluation, indent=2, sort_keys=True
                ) + "\n"
            )

            nvram_after = box.nvram_boot_variables()
            (self.dir / "nvram.after.json").write_text(
                json.dumps(
                    nvram_after, indent=2, sort_keys=True
                ) + "\n"
            )
            guard_after = sha256(self.cfg.guard)
            guard_unchanged = guard_after == guard_before
            nvram_unchanged = (
                persistent_boot_state(nvram_after)
                == persistent_boot_state(nvram_before)
            )

            if not guard_unchanged:
                summary["status"] = "FAIL"
                summary["failed"].append(
                    "guard-disk-unchanged"
                )
            if not nvram_unchanged:
                summary["status"] = "FAIL"
                summary["failed"].append(
                    "persistent-nvram-unchanged"
                )

            self.event(
                "audit-complete",
                status=summary["status"],
                failed=summary["failed"],
                warnings=summary["warnings"],
                guard_unchanged=guard_unchanged,
                persistent_nvram_unchanged=nvram_unchanged,
            )
            return self.result(
                summary["status"],
                summary=summary,
                facts=evaluation["facts"],
                guard_unchanged=guard_unchanged,
                persistent_nvram_unchanged=nvram_unchanged,
                evidence={
                    "checks": str(
                        self.dir / "checks.json"
                    ),
                    "sections": str(
                        self.dir / "sections.json"
                    ),
                    "probe_output": str(
                        self.dir / "probe-output.log"
                    ),
                },
            )
        except Exception as exc:
            self.event("audit-fail", error=repr(exc))
            return self.result(
                "FAIL",
                error=repr(exc),
                summary={
                    "status": "FAIL",
                    "failed": ["harness"],
                    "warnings": [],
                },
            )
        finally:
            if keyboard is not None:
                try:
                    keyboard.ctrl_alt_fn(2)
                    time.sleep(0.5)
                    self.event("returned-to-graphical-vt", vt=2)
                except Exception as exc:
                    self.event("graphical-vt-return-failed", error=repr(exc))
            box.logoff()
            self.events.close()


def audit_installed(cfg=None):
    return InstalledAudit(cfg).run()
