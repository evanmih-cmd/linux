import hashlib
import json
import os
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

from config import Config


YAST_NS = "http://www.suse.com/1.0/yast2ns"
ET.register_namespace("", YAST_NS)
ET.register_namespace("config", "http://www.suse.com/1.0/configns")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for chunk in iter(lambda: src.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_credentials(cfg):
    if not cfg.credentials.exists():
        return {}
    data = json.loads(cfg.credentials.read_text())
    allowed = {"recovery", "pin", "root"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise RuntimeError(
            "unknown VM credential keys in "
            f"{cfg.credentials}: {', '.join(unknown)}"
        )
    return {
        key: value
        for key, value in data.items()
        if key in allowed and isinstance(value, str) and value
    }


def _child(parent, name):
    return parent.find(f"{{{YAST_NS}}}{name}")


def _ask_path(ask):
    node = _child(ask, "path")
    return None if node is None else node.text


def render_runtime_profile(cfg, destination, credentials):
    tree = ET.parse(cfg.profile)
    root = tree.getroot()

    partitioning = _child(root, "partitioning")
    physical = list(partitioning)[0]
    partitions = _child(physical, "partitions")
    outer = list(partitions)[1]
    crypt_key = _child(outer, "crypt_key")

    users = _child(root, "users")
    root_user = list(users)[0]
    user_password = _child(root_user, "user_password")

    general = _child(root, "general")
    ask_list = _child(general, "ask-list")

    embedded = []
    if "recovery" in credentials:
        crypt_key.text = credentials["recovery"]
        for ask in list(ask_list):
            if _ask_path(ask) == "partitioning,0,partitions,1,crypt_key":
                ask_list.remove(ask)
        embedded.append("recovery")

    if "root" in credentials:
        user_password.text = credentials["root"]
        for ask in list(ask_list):
            if _ask_path(ask) == "users,0,user_password":
                ask_list.remove(ask)
        embedded.append("root")

    if "pin" in credentials:
        for ask in list(ask_list):
            title = _child(ask, "title")
            if title is not None and title.text == "Portable workstation TPM credential":
                ask_list.remove(ask)
        embedded.append("pin")

    if len(list(ask_list)) == 0:
        general.remove(ask_list)

    scripts = _child(root, "scripts")
    pre_scripts = _child(scripts, "pre-scripts")
    pre = list(pre_scripts)[0]
    source = _child(pre, "source")
    source.text = """
(
  while [ ! -r /var/log/YaST2/y2log ]; do sleep 1; done
  exec tail -n +1 -F /var/log/YaST2/y2log > /dev/ttyS0 2>&1
) &
( sleep 2; printf 'VMBENCH_PROFILE_READY\n' > /dev/ttyS0 ) &
"""

    tree.write(destination, encoding="UTF-8", xml_declaration=True)

    missing = [key for key in ("recovery", "pin", "root") if key not in credentials]
    return {
        "embedded": embedded,
        "missing": missing,
    }


SNAPSHOT_SOURCE_HASHES = {
    "usr/share/YaST2/lib/bootloader/autoyast_converter.rb":
        "32e1f4c5138b849333788019444b097c72fe75b5fb15d5d1fe26e31ced8d86c3",
    "usr/share/YaST2/lib/bootloader/bls.rb":
        "8e3fe14b84a645ef33352586baaefc02561e78a7e2a0e05e171b5ee977ea4743",
    "usr/share/YaST2/lib/bootloader/systemdboot.rb":
        "331c55a9575f86bf610c12e7e4dda9348b010b1cfda0264d5f9f4eb9b8bc5d58",
    "usr/share/YaST2/lib/y2storage/proposal/autoinst_drive_planner.rb":
        "fbad3863a854b608016f9e9676a1d8b9226fe8ea4458cad347c4bda2136013b5",
    "usr/share/YaST2/modules/Lan.rb":
        "21147713babda7100843df42b8c8685156f3385bb65eaa00a280fbae19e1c429",
    "usr/bin/keyctl":
        "a09d1ab9ecb5270d571ac92a703e7b10f976e5e42300a9a1e0a71386fb17429c",
    "usr/lib64/libkeyutils.so.1.10":
        "a16faea6d85e33aa6c3f10f293ed4b4b2d30faa1cee3be25ab9710fca510281e",
}

PATCH_NAMES = (
    "auth_patch",
    "update_nvram_patch",
    "network_patch",
    "portable_layout_patch",
)


def _verified_snapshot_source(cfg):
    source = cfg.snapshot_instsys_source
    if not source.is_dir():
        raise RuntimeError(f"exact Snapshot installer source is missing: {source}")

    errors = []
    for relative, expected in SNAPSHOT_SOURCE_HASHES.items():
        path = source / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
            continue
        actual = sha256(path)
        if actual != expected:
            errors.append(
                f"{relative}: expected {expected}, got {actual}"
            )

    if errors:
        raise RuntimeError(
            "Snapshot20260930 installer source verification failed:\n  - "
            + "\n  - ".join(errors)
        )
    return source


def _patchset(cfg):
    result = []
    for name in PATCH_NAMES:
        path = getattr(cfg, name)
        if not path.is_file():
            raise RuntimeError(f"source-controlled installer patch missing: {path}")
        result.append((name, path, sha256(path)))
    return result


def _apply_patch(inst, patch):
    proc = subprocess.run(
        ["patch", "--batch", "--forward", "--fuzz=0", "-p1"],
        cwd=inst,
        stdin=open(patch, "rb"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
    )
    if proc.returncode != 0:
        output = proc.stdout.decode(errors="replace")
        raise RuntimeError(f"cannot apply {patch.name}:\n{output}")


def _copy_snapshot_instsys(source, inst):
    for relative in SNAPSHOT_SOURCE_HASHES:
        src = source / relative
        dst = inst / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    keyutils_link = inst / "usr/lib64/libkeyutils.so.1"
    keyutils_link.symlink_to("libkeyutils.so.1.10")


def build_oemdrv(cfg=None):
    cfg = cfg or Config()
    ET.parse(cfg.profile)
    credentials = load_credentials(cfg)

    source = _verified_snapshot_source(cfg)
    patches = _patchset(cfg)
    profile_sha = sha256(cfg.profile)
    patchset_material = "\n".join(
        f"{name}={digest}" for name, _, digest in patches
    )
    patch_sha = hashlib.sha256(patchset_material.encode()).hexdigest()

    cred_stat = cfg.credentials.stat() if cfg.credentials.exists() else None
    opaque_input = (
        f"{profile_sha}\n{patch_sha}\n"
        f"{cred_stat.st_mtime_ns if cred_stat else 0}\n"
        f"{cred_stat.st_size if cred_stat else 0}\n"
        f"{time.time_ns()}\n"
    )
    ident = hashlib.sha256(opaque_input.encode()).hexdigest()[:16]

    xorriso = cfg.cache / "tools/rootless/xorriso/usr/bin/xorriso"
    xorriso_lib = cfg.cache / (
        "tools/rootless/xorriso/usr/lib/x86_64-linux-gnu"
    )

    cfg.bench.mkdir(parents=True, exist_ok=True)
    build_root = cfg.bench / f"oem-root-{ident}"
    iso = cfg.bench / f"oemdrv-{ident}.iso"

    if build_root.exists():
        shutil.rmtree(build_root)
    build_root.mkdir(parents=True)

    credential_mode = render_runtime_profile(
        cfg,
        build_root / "autoinst.xml",
        credentials,
    )

    inst = build_root / "linux/suse/x86_64-tw/inst-sys"
    inst.mkdir(parents=True)
    _copy_snapshot_instsys(source, inst)

    # All installer behavior deltas are applied here from repository sources.
    # No prepatched OEMDRV/cache tree is an input to this build.
    for _, patch, _ in patches:
        _apply_patch(inst, patch)

    for orig in inst.rglob("*.orig"):
        orig.unlink()

    pin_file = inst / "etc/desktop-linux-tpm2-pin"
    pin_file.parent.mkdir(parents=True, exist_ok=True)
    pin_file.write_text(credentials.get("pin", ""))
    pin_file.chmod(0o600)

    (inst / f".update.{ident}").touch()

    dud = build_root / "linux/suse/x86_64-tw/dud.config"
    dud.write_text(
        f"UpdateID:\t{ident}\n"
        "UpdateProduct:\topenSUSE Tumbleweed\n"
        "UpdateInstaller:\tyast\n"
        f"UpdateName:\tDesktop-Linux vmbench {ident}\n"
    )

    (build_root / "BASE-ISO.sha256").write_text(
        "0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99  "
        "openSUSE-Tumbleweed-DVD-x86_64-Snapshot20260930-Media.iso\n"
    )
    (build_root / "SOURCE-IDENTITY.txt").write_text(
        "snapshot=Snapshot20260930\n"
        "source-mode=verified-clean-instsys-files\n"
        f"profile-sha256={profile_sha}\n"
        f"patchset-sha256={patch_sha}\n"
        + patchset_material + "\n"
    )

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(xorriso_lib)
    subprocess.run(
        [
            str(xorriso), "-as", "mkisofs",
            "-R", "-J", "-V", "OEMDRV",
            "-o", str(iso), str(build_root),
        ],
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    shutil.rmtree(build_root)

    (cfg.bench / "current-oem.path").write_text(str(iso) + "\n")
    (cfg.bench / "current-build.txt").write_text(
        f"PROFILE_SHA={profile_sha}\n"
        f"PATCHSET_SHA={patch_sha}\n"
        + "".join(
            f"{name.upper()}_SHA={digest}\n"
            for name, _, digest in patches
        )
        + f"ID={ident}\n"
        f"ISO={iso}\n"
        f"EMBEDDED={','.join(credential_mode['embedded'])}\n"
        f"MISSING={','.join(credential_mode['missing'])}\n"
    )

    for stale in cfg.bench.glob("oemdrv-*.iso"):
        if stale != iso:
            stale.unlink()

    return {
        "id": ident,
        "iso": iso,
        "profile_sha": profile_sha,
        "patch_sha": patch_sha,
        "patches": {name: digest for name, _, digest in patches},
        "credentials": credential_mode,
    }
