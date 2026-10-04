import hashlib
import json
import os
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

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


SNAPSHOT_ISO_SHA256 = "0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99"

SNAPSHOT_RPM_INPUTS = {
    "/x86_64/yast2-bootloader-5.0.42-1.1.x86_64.rpm": (
        "usr/share/YaST2/lib/bootloader/autoyast_converter.rb",
        "usr/share/YaST2/lib/bootloader/bls.rb",
        "usr/share/YaST2/lib/bootloader/systemdboot.rb",
    ),
    "/x86_64/yast2-storage-ng-5.0.50-1.1.x86_64.rpm": (
        "usr/share/YaST2/lib/y2storage/proposal/autoinst_drive_planner.rb",
    ),
    "/noarch/yast2-network-5.0.7-1.2.noarch.rpm": (
        "usr/share/YaST2/modules/Lan.rb",
    ),
    "/x86_64/keyutils-1.6.3-7.9.x86_64.rpm": (
        "usr/bin/keyctl",
    ),
    "/x86_64/libkeyutils1-1.6.3-7.9.x86_64.rpm": (
        "usr/lib64/libkeyutils.so.1.10",
    ),
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


def _snapshot_source_errors(source):
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
    return errors


def _rebuild_snapshot_source(cfg, source):
    if not cfg.official_iso.is_file():
        raise RuntimeError(f"official Snapshot ISO is missing: {cfg.official_iso}")

    actual_iso = sha256(cfg.official_iso)
    if actual_iso != SNAPSHOT_ISO_SHA256:
        raise RuntimeError(
            "official Snapshot ISO verification failed: "
            f"expected {SNAPSHOT_ISO_SHA256}, got {actual_iso}"
        )

    xorriso = cfg.cache / "tools/rootless/xorriso/usr/bin/xorriso"
    xorriso_lib = cfg.cache / "tools/rootless/xorriso/usr/lib/x86_64-linux-gnu"
    rpm2cpio = cfg.cache / "tools/rpm-extract/root/usr/lib/rpm/rpm2cpio.sh"
    zstd_bin = cfg.cache / "tools/rootless/zstd/root/usr/bin"
    cpio = cfg.cache / "tools/rootless/cpio/usr/bin/cpio"

    required_tools = (xorriso, rpm2cpio, zstd_bin / "unzstd", cpio)
    missing_tools = [str(path) for path in required_tools if not path.exists()]
    if missing_tools:
        raise RuntimeError(
            "Snapshot source extraction tools are missing: "
            + ", ".join(missing_tools)
        )

    import tempfile

    source.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="snapshot20260930-source-", dir=source.parent
    ) as td:
        work = Path(td)
        clean = work / "clean"
        clean.mkdir()
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = str(xorriso_lib)
        extract_env = os.environ.copy()
        extract_env["PATH"] = (
            f"{zstd_bin}:{cpio.parent}:" + extract_env.get("PATH", "")
        )

        for rpm_path, relative_paths in SNAPSHOT_RPM_INPUTS.items():
            rpm_file = work / Path(rpm_path).name
            subprocess.run(
                [
                    str(xorriso), "-osirrox", "on",
                    "-indev", str(cfg.official_iso),
                    "-extract", rpm_path, str(rpm_file),
                ],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            payload = work / (rpm_file.name + ".root")
            payload.mkdir()
            producer = subprocess.Popen(
                ["/bin/sh", str(rpm2cpio), str(rpm_file)],
                stdout=subprocess.PIPE,
                env=extract_env,
            )
            try:
                consumer = subprocess.run(
                    [str(cpio), "-idmu", "--quiet"],
                    cwd=payload,
                    stdin=producer.stdout,
                    env=extract_env,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            finally:
                if producer.stdout is not None:
                    producer.stdout.close()
            producer_rc = producer.wait()
            if producer_rc != 0 or consumer.returncode != 0:
                raise RuntimeError(
                    f"cannot extract {rpm_path}: "
                    f"rpm2cpio={producer_rc}, cpio={consumer.returncode}, "
                    f"stderr={consumer.stderr.decode(errors='replace')}"
                )

            for relative in relative_paths:
                src = payload / relative
                if not src.is_file():
                    raise RuntimeError(
                        f"{rpm_path} does not contain required {relative}"
                    )
                dst = clean / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        (clean / "usr/lib64/libkeyutils.so.1").symlink_to(
            "libkeyutils.so.1.10"
        )

        errors = _snapshot_source_errors(clean)
        if errors:
            raise RuntimeError(
                "Snapshot20260930 source reconstructed from verified ISO "
                "but pinned file verification failed:\n  - "
                + "\n  - ".join(errors)
            )

        (clean / "PROVENANCE.txt").write_text(
            "Snapshot: openSUSE Tumbleweed Snapshot20260930\n"
            f"Official ISO SHA-256: {SNAPSHOT_ISO_SHA256}\n"
            "Source mode: extracted directly from pinned RPM paths on the "
            "verified official ISO.\n"
        )

        if source.exists():
            shutil.rmtree(source)
        shutil.copytree(clean, source, symlinks=True)


def _verified_snapshot_source(cfg):
    source = cfg.snapshot_instsys_source
    errors = _snapshot_source_errors(source) if source.is_dir() else ["missing source cache"]
    if errors:
        _rebuild_snapshot_source(cfg, source)
        errors = _snapshot_source_errors(source)
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
