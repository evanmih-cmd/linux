#!/usr/bin/env python3
"""
Interactive storage stage for the portable installer.

This is intentionally the only destructive decision point. It discovers only
removable/USB whole disks, asks the operator to select a target and one of two
modes, then materializes the exact storage graph expected by autoinstall:

  fresh
      Recreate GPT, ESP, LUKS2, Btrfs and all subvolumes.

  reinstall
      Reuse the existing layout, preserve persistent subvolumes, snapshot the
      old root, replace only @root, and reuse the existing encrypted volume.

The script then rewrites only the generated storage block and password hash in
/autoinstall.yaml. Subiquity reloads the configuration after early-commands.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

MAPPER = "portable-root"
ROOT_DEV = f"/dev/mapper/{MAPPER}"
ESP_PARTLABEL = "PORTABLE_EFI"
CRYPT_PARTLABEL = "PORTABLE_CRYPT"
ESP_FSLABEL = "PORTABLE_EFI"
ROOT_FSLABEL = "PORTABLE_ROOT"
SUBVOLUMES = ("@root", "@home", "@appdata", "@logs", "@snapshots")
STATE_DIR = Path("/run/portable-installer")
TOP = Path("/mnt/portable-top")
ESP_MNT = Path("/mnt/portable-esp")


def run(args, *, check=True, input_text=None, capture=False):
    kwargs = {
        "check": check,
        "text": True,
    }
    if input_text is not None:
        kwargs["input"] = input_text
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    return subprocess.run(args, **kwargs)


def out(args) -> str:
    return run(args, capture=True).stdout.strip()


def human_size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError


def lsblk():
    data = json.loads(
        out(
            [
                "lsblk",
                "-J",
                "-b",
                "-o",
                "NAME,PATH,SIZE,MODEL,SERIAL,TRAN,RM,TYPE,RO,MOUNTPOINTS,PARTLABEL,FSTYPE,LABEL,UUID",
            ]
        )
    )
    return data["blockdevices"]


def block_parent(path: str) -> str | None:
    try:
        pk = out(["lsblk", "-ndo", "PKNAME", path])
    except subprocess.CalledProcessError:
        return None
    return f"/dev/{pk}" if pk else path


def installer_disks() -> set[str]:
    result: set[str] = set()
    for mountpoint in ("/cdrom", "/isodevice", "/run/live/medium"):
        proc = run(
            ["findmnt", "-n", "-o", "SOURCE", mountpoint],
            check=False,
            capture=True,
        )
        source = proc.stdout.strip()
        if not source.startswith("/dev/"):
            continue
        parent = block_parent(source)
        if parent:
            result.add(parent)
    return result


def candidates():
    excluded = installer_disks()
    result = []
    for dev in lsblk():
        if dev.get("type") != "disk" or int(dev.get("ro") or 0):
            continue
        path = dev["path"]
        if path in excluded:
            continue
        removable = int(dev.get("rm") or 0) == 1
        usb = (dev.get("tran") or "").lower() == "usb"
        if not (removable or usb):
            continue
        result.append(dev)
    return result


def prompt(text: str) -> str:
    return input(text).strip()


def secret(text: str) -> str:
    # stdin is redirected to the installer VT; getpass disables echo there.
    return getpass.getpass(text)


def choose_disk():
    disks = candidates()
    if not disks:
        raise SystemExit("No eligible removable/USB target disks found.")

    print("\nEligible target disks:\n")
    for idx, dev in enumerate(disks, 1):
        model = (dev.get("model") or "").strip() or "unknown-model"
        serial = (dev.get("serial") or "").strip() or "no-serial"
        print(
            f"  {idx}. {dev['path']:12} {human_size(int(dev['size'])):>10}  "
            f"{model}  serial={serial}"
        )

    while True:
        value = prompt("\nSelect target disk number: ")
        if value.isdigit() and 1 <= int(value) <= len(disks):
            return disks[int(value) - 1]
        print("Invalid selection.")


def partitions(disk: str):
    rows = []
    text = out(
        [
            "lsblk",
            "-nrpo",
            "PATH,PARTLABEL,FSTYPE,LABEL,UUID",
            disk,
        ]
    )
    for line in text.splitlines():
        parts = line.split(None, 4)
        while len(parts) < 5:
            parts.append("")
        path, partlabel, fstype, label, uuid = parts
        if path == disk:
            continue
        rows.append(
            {
                "path": path,
                "partlabel": partlabel,
                "fstype": fstype,
                "label": label,
                "uuid": uuid,
            }
        )
    return rows


def existing_layout(disk: str):
    esp = crypt = None
    for p in partitions(disk):
        if p["partlabel"] == ESP_PARTLABEL:
            esp = p
        elif p["partlabel"] == CRYPT_PARTLABEL:
            crypt = p
    if not esp or not crypt:
        return None
    if esp["fstype"] not in ("vfat", "fat", "fat32"):
        return None
    if crypt["fstype"] != "crypto_LUKS":
        return None
    return esp["path"], crypt["path"]


def unmount_children(disk: str):
    text = out(["lsblk", "-nrpo", "PATH,MOUNTPOINTS", disk])
    rows = [line.split(None, 1) for line in text.splitlines()]
    for row in reversed(rows):
        if len(row) < 2:
            continue
        path, mounts = row
        if path == disk:
            continue
        for mnt in reversed(mounts.split()):
            run(["umount", mnt], check=False)


def close_mapper_if_safe(expected_part: str | None = None):
    proc = run(["cryptsetup", "status", MAPPER], check=False, capture=True)
    if proc.returncode != 0:
        return
    if expected_part:
        backing = None
        for line in proc.stdout.splitlines():
            if "device:" in line:
                backing = line.split("device:", 1)[1].strip()
                break
        if backing and os.path.realpath(backing) != os.path.realpath(expected_part):
            raise SystemExit(
                f"{ROOT_DEV} is already active on unexpected backing device {backing}."
            )
    run(["cryptsetup", "close", MAPPER])


def confirm_fresh(dev):
    serial = (dev.get("serial") or "").strip()
    token = serial if serial and serial != "no-serial" else dev["path"]
    print(
        "\nFRESH mode DESTROYS ALL DATA on the selected target.\n"
        f"Target: {dev['path']}  {dev.get('model') or ''}  serial={serial or 'unknown'}\n"
    )
    typed = prompt(f"Type exactly ERASE {token} to continue: ")
    if typed != f"ERASE {token}":
        raise SystemExit("Destructive confirmation did not match.")


def get_new_luks_passphrase():
    while True:
        first = secret("New LUKS passphrase: ")
        second = secret("Repeat LUKS passphrase: ")
        if first != second:
            print("Passphrases do not match.")
            continue
        if len(first) < 12:
            print("Passphrase must be at least 12 characters.")
            continue
        return first


def get_user_password():
    while True:
        first = secret("Local account password: ")
        second = secret("Repeat local account password: ")
        if first != second:
            print("Passwords do not match.")
            continue
        if len(first) < 12:
            print("Password must be at least 12 characters.")
            continue
        return first


def create_partitions(disk: str):
    run(["wipefs", "-a", disk])
    run(["parted", "-s", disk, "mklabel", "gpt"])
    run(
        [
            "parted",
            "-s",
            disk,
            "mkpart",
            ESP_PARTLABEL,
            "fat32",
            "1MiB",
            "1025MiB",
        ]
    )
    run(["parted", "-s", disk, "set", "1", "esp", "on"])
    run(["parted", "-s", disk, "name", "1", ESP_PARTLABEL])
    run(
        [
            "parted",
            "-s",
            disk,
            "mkpart",
            CRYPT_PARTLABEL,
            "1025MiB",
            "100%",
        ]
    )
    run(["parted", "-s", disk, "name", "2", CRYPT_PARTLABEL])
    run(["partprobe", disk], check=False)
    run(["udevadm", "settle"])

    layout = existing_layout_paths(disk)
    if not layout:
        raise SystemExit("Could not rediscover freshly created partitions.")
    return layout


def existing_layout_paths(disk: str):
    esp = crypt = None
    text = out(["lsblk", "-nrpo", "PATH,PARTLABEL", disk])
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        path, label = parts
        if label == ESP_PARTLABEL:
            esp = path
        elif label == CRYPT_PARTLABEL:
            crypt = path
    if esp and crypt:
        return esp, crypt
    return None


def open_luks(crypt_part: str, passphrase: str):
    close_mapper_if_safe(crypt_part)
    run(
        ["cryptsetup", "open", "--type", "luks2", "--key-file=-", crypt_part, MAPPER],
        input_text=passphrase,
    )


def mkfs_fresh(esp_part: str, crypt_part: str, passphrase: str):
    run(["mkfs.fat", "-F", "32", "-n", ESP_FSLABEL, esp_part])
    run(
        [
            "cryptsetup",
            "luksFormat",
            "--batch-mode",
            "--type",
            "luks2",
            "--key-file=-",
            crypt_part,
        ],
        input_text=passphrase,
    )
    open_luks(crypt_part, passphrase)
    run(["mkfs.btrfs", "-f", "-L", ROOT_FSLABEL, ROOT_DEV])

    TOP.mkdir(parents=True, exist_ok=True)
    run(["mount", "-t", "btrfs", "-o", "subvolid=5", ROOT_DEV, str(TOP)])
    try:
        for name in SUBVOLUMES:
            run(["btrfs", "subvolume", "create", str(TOP / name)])
    finally:
        run(["umount", str(TOP)])


def prepare_reinstall(esp_part: str, crypt_part: str, passphrase: str):
    open_luks(crypt_part, passphrase)

    fstype = out(["blkid", "-s", "TYPE", "-o", "value", ROOT_DEV])
    label = out(["blkid", "-s", "LABEL", "-o", "value", ROOT_DEV])
    if fstype != "btrfs" or label != ROOT_FSLABEL:
        raise SystemExit("Existing encrypted volume is not the expected Btrfs layout.")

    TOP.mkdir(parents=True, exist_ok=True)
    ESP_MNT.mkdir(parents=True, exist_ok=True)
    run(["mount", "-t", "btrfs", "-o", "subvolid=5", ROOT_DEV, str(TOP)])
    try:
        missing = [name for name in SUBVOLUMES if not (TOP / name).exists()]
        if missing:
            raise SystemExit(
                "Existing layout is missing required subvolumes: " + ", ".join(missing)
            )

        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        root = TOP / "@root"
        root_snapshot = TOP / "@snapshots" / f"root-pre-reinstall-{stamp}"
        run(["btrfs", "subvolume", "snapshot", "-r", str(root), str(root_snapshot)])

        run(["mount", esp_part, str(ESP_MNT)])
        try:
            esp_backup = TOP / "@snapshots" / f"esp-pre-reinstall-{stamp}.tar"
            run(["tar", "-C", str(ESP_MNT), "-cpf", str(esp_backup), "."])
        finally:
            run(["umount", str(ESP_MNT)])

        run(["btrfs", "subvolume", "delete", str(root)])
        run(["btrfs", "subvolume", "create", str(root)])
    finally:
        run(["umount", str(TOP)])


def password_hash(password: str) -> str:
    proc = run(
        ["openssl", "passwd", "-6", "-stdin"],
        input_text=password + "\n",
        capture=True,
    )
    value = proc.stdout.strip()
    if not value.startswith("$6$"):
        raise SystemExit("Failed to generate local account password hash.")
    return value


def uuid_of(path: str) -> str:
    value = out(["blkid", "-s", "UUID", "-o", "value", path])
    if not value:
        raise SystemExit(f"Could not determine UUID for {path}.")
    return value


def patch_autoinstall(
    path: Path,
    *,
    password_hash_value: str,
    disk: str,
    esp_part: str,
    esp_uuid: str,
):
    text = path.read_text()

    text = re.sub(
        r'^\s*password:.*# GENERATED_PASSWORD\s*$',
        f'    password: "{password_hash_value}" # GENERATED_PASSWORD',
        text,
        count=1,
        flags=re.MULTILINE,
    )

    storage = f"""  # BEGIN GENERATED STORAGE
  storage:
    swap:
      size: 0
    grub:
      install_devices:
        - {disk}
      update_nvram: false
      reorder_uefi: false
      remove_duplicate_entries: false
      probe_additional_os: false
    config:
      - id: target-disk
        type: device
        path: {disk}

      - id: esp-device
        type: device
        path: {esp_part}
      - id: esp-format
        type: format
        fstype: fat32
        volume: esp-device
        preserve: true
      - id: esp-mount
        type: mount
        device: esp-format
        path: /efi
        options: umask=0077

      - id: root-device
        type: device
        path: {ROOT_DEV}
      - id: root-format
        type: format
        fstype: btrfs
        volume: root-device
        preserve: true

      - id: root-mount
        type: mount
        device: root-format
        path: /
        options: subvol=@root,compress=zstd:1,noatime

      - id: home-mount
        type: mount
        spec: {ROOT_DEV}
        fstype: btrfs
        path: /home
        options: subvol=@home,compress=zstd:1,noatime

      - id: appdata-mount
        type: mount
        spec: {ROOT_DEV}
        fstype: btrfs
        path: /persist
        options: subvol=@appdata,compress=zstd:1,noatime

      - id: logs-mount
        type: mount
        spec: {ROOT_DEV}
        fstype: btrfs
        path: /var/log
        options: subvol=@logs,compress=zstd:1,noatime

      - id: snapshots-mount
        type: mount
        spec: {ROOT_DEV}
        fstype: btrfs
        path: /.snapshots
        options: subvol=@snapshots,compress=zstd:1,noatime

      - id: tmp-mount
        type: mount
        spec: tmpfs
        fstype: tmpfs
        path: /tmp
        options: mode=1777,nosuid,nodev
  # END GENERATED STORAGE"""

    pattern = re.compile(
        r"^  # BEGIN GENERATED STORAGE\n.*?^  # END GENERATED STORAGE$",
        flags=re.MULTILINE | re.DOTALL,
    )
    if not pattern.search(text):
        raise SystemExit("Generated storage markers are missing from autoinstall config.")
    text = pattern.sub(storage, text, count=1)
    path.write_text(text)


def write_state(**values):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = STATE_DIR / "state.env"
    state.write_text(
        "".join(f"{key}={shlex.quote(str(value))}\n" for key, value in values.items())
    )
    os.chmod(state, 0o600)


def main():
    if os.geteuid() != 0:
        raise SystemExit("storage-stage.py must run as root.")
    if len(sys.argv) != 2:
        raise SystemExit("usage: storage-stage.py /autoinstall.yaml")

    config = Path(sys.argv[1])
    dev = choose_disk()
    disk = dev["path"]
    old_layout = existing_layout(disk)

    print("\nModes:")
    print("  1. fresh      - erase target and create a new portable layout")
    if old_layout:
        print("  2. reinstall  - preserve persistent subvolumes, replace only system root")
    else:
        print("  2. reinstall  - unavailable (expected existing layout not found)")

    while True:
        mode_value = prompt("\nSelect mode [1/2]: ")
        if mode_value == "1":
            mode = "fresh"
            break
        if mode_value == "2" and old_layout:
            mode = "reinstall"
            break
        print("Invalid selection.")

    unmount_children(disk)

    if mode == "fresh":
        confirm_fresh(dev)
        luks_pass = get_new_luks_passphrase()
        esp_part, crypt_part = create_partitions(disk)
        mkfs_fresh(esp_part, crypt_part, luks_pass)
    else:
        esp_part, crypt_part = old_layout
        luks_pass = secret("Existing LUKS passphrase: ")
        prepare_reinstall(esp_part, crypt_part, luks_pass)

    user_password = get_user_password()
    user_hash = password_hash(user_password)

    luks_uuid = uuid_of(crypt_part)
    btrfs_uuid = uuid_of(ROOT_DEV)
    esp_uuid = uuid_of(esp_part)

    patch_autoinstall(
        config,
        password_hash_value=user_hash,
        disk=disk,
        esp_part=esp_part,
        esp_uuid=esp_uuid,
    )
    write_state(
        MODE=mode,
        TARGET_DISK=disk,
        ESP_PART=esp_part,
        CRYPT_PART=crypt_part,
        LUKS_UUID=luks_uuid,
        BTRFS_UUID=btrfs_uuid,
        ESP_UUID=esp_uuid,
    )

    # Do not persist either entered secret. The opened mapper is intentionally
    # left active for Curtin; runtime unlock is configured by postinstall.
    luks_pass = None
    user_password = None

    print("\nStorage stage complete. Returning to unattended installation.")


if __name__ == "__main__":
    main()
