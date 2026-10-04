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


def render_runtime_profile(cfg, destination, credentials, *, vm_observability=True, target_device=None):
    tree = ET.parse(cfg.profile)
    root = tree.getroot()

    partitioning = _child(root, "partitioning")
    physical = list(partitioning)[0]
    target_device = target_device or cfg.vm_target_device
    device = _child(physical, "device")
    if device is None:
        raise RuntimeError("canonical profile is missing physical target device")
    device.text = target_device
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
    if scripts is not None:
        root.remove(scripts)

    if vm_observability:
        scripts = ET.SubElement(root, f"{{{YAST_NS}}}scripts")
        pre_scripts = ET.SubElement(
            scripts,
            f"{{{YAST_NS}}}pre-scripts",
            {"{http://www.suse.com/1.0/configns}type": "list"},
        )
        pre = ET.SubElement(pre_scripts, f"{{{YAST_NS}}}script")
        ET.SubElement(pre, f"{{{YAST_NS}}}filename").text = "vmbench-observability"
        ET.SubElement(pre, f"{{{YAST_NS}}}interpreter").text = "shell"
        ET.SubElement(
            pre,
            f"{{{YAST_NS}}}debug",
            {"{http://www.suse.com/1.0/configns}type": "boolean"},
        ).text = "false"
        ET.SubElement(
            pre,
            f"{{{YAST_NS}}}feedback",
            {"{http://www.suse.com/1.0/configns}type": "boolean"},
        ).text = "false"
        ET.SubElement(pre, f"{{{YAST_NS}}}source").text = """
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
        "usr/share/YaST2/lib/y2storage/encryption.rb",
    ),
    "/noarch/yast2-network-5.0.7-1.2.noarch.rpm": (
        "usr/share/YaST2/modules/Lan.rb",
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
    "usr/share/YaST2/lib/y2storage/encryption.rb":
        "32bf1c4f77a1937f20fb72a9895ec90e84839f001657ffeafd86850114bbe036",
    "usr/share/YaST2/modules/Lan.rb":
        "21147713babda7100843df42b8c8685156f3385bb65eaa00a280fbae19e1c429",
}

PATCH_NAMES = (
    "auth_patch",
    "update_nvram_patch",
    "network_patch",
)


OEMDRV_STATIC_FILES = {
    "BASE-ISO.sha256",
    "SOURCE-IDENTITY.txt",
    "SYMLINKS",
    "SHA256SUMS",
    "autoinst.xml",
    "linux/suse/x86_64-tw/dud.config",
    "linux/suse/x86_64-tw/inst-sys/etc/desktop-linux-tpm2-pin",
    "linux/suse/x86_64-tw/inst-sys/usr/share/YaST2/lib/bootloader/autoyast_converter.rb",
    "linux/suse/x86_64-tw/inst-sys/usr/share/YaST2/lib/bootloader/bls.rb",
    "linux/suse/x86_64-tw/inst-sys/usr/share/YaST2/lib/bootloader/systemdboot.rb",
    "linux/suse/x86_64-tw/inst-sys/usr/share/YaST2/lib/y2storage/proposal/autoinst_drive_planner.rb",
    "linux/suse/x86_64-tw/inst-sys/usr/share/YaST2/lib/y2storage/encryption.rb",
    "linux/suse/x86_64-tw/inst-sys/usr/share/YaST2/modules/Lan.rb",
}

OEMDRV_SYMLINKS = {}


POST_PATCH_HASHES = {
    "usr/share/YaST2/lib/bootloader/autoyast_converter.rb":
        "7ac0c97c6d3156f5093c85dce1a906c56c64e128fed2d9281ce4d5b9d7d02612",
    "usr/share/YaST2/lib/bootloader/bls.rb":
        "2551dac04b782921aa325f429e211b8adbbae1d36159cf101f7d781610b2d4e5",
    "usr/share/YaST2/lib/bootloader/systemdboot.rb":
        "331c55a9575f86bf610c12e7e4dda9348b010b1cfda0264d5f9f4eb9b8bc5d58",
    "usr/share/YaST2/lib/y2storage/proposal/autoinst_drive_planner.rb":
        "8dbebc3a2b83fcc67780e16e0c40d3e5eff4b80d793403123208cf6b2226baa8",
    "usr/share/YaST2/lib/y2storage/encryption.rb":
        "7150ecfe3fc8e0e4766c6a7ced9d7108588d7a20e11d0c37db4ec62e2b7576ab",
    "usr/share/YaST2/modules/Lan.rb":
        "58231f7be60bfed86f44b8a5294c0bc405c8293da3939d407658bf76fe2535f0",
}


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

def verify_patchset_against_snapshot(cfg=None):
    cfg = cfg or Config()
    source = _verified_snapshot_source(cfg)
    patches = _patchset(cfg)

    import tempfile

    with tempfile.TemporaryDirectory(prefix="patchset-proof-") as td:
        inst = Path(td)
        _copy_snapshot_instsys(source, inst)

        for _, patch, _ in patches:
            _apply_patch(inst, patch)

        rejects = sorted(
            path.relative_to(inst).as_posix()
            for path in inst.rglob("*.rej")
        )
        if rejects:
            raise RuntimeError(
                "patchset left reject files: " + ", ".join(rejects)
            )

        for original in inst.rglob("*.orig"):
            original.unlink()

        encryption_source = (
            inst / "usr/share/YaST2/lib/y2storage/encryption.rb"
        ).read_text()
        required_tpm_activation = (
            """def authentication=(value)
      save_userdata(:encryption_authentication, value)
      adjust_crypt_options""",
            'authentication&.is?(:tpm2, :"tpm2+pin")',
            'self.crypt_options |= ["tpm2-device=auto"]',
            'self.crypt_options -= ["tpm2-device=auto"]',
        )
        missing_tpm_activation = [
            snippet
            for snippet in required_tpm_activation
            if snippet not in encryption_source
        ]
        if missing_tpm_activation:
            raise RuntimeError(
                "systemd-FDE TPM crypttab lifecycle invariant missing: "
                + repr(missing_tpm_activation)
            )

        if ":tpm2+pin" in encryption_source:
            raise RuntimeError(
                "invalid Ruby TPM2+PIN symbol form present; use :\"tpm2+pin\""
            )

        bls_source = (
            inst / "usr/share/YaST2/lib/bootloader/bls.rb"
        ).read_text()
        required_initial_tpm_prediction = (
            'enroll_env["SDB_ADD_INITIAL_COMPONENT"] = "1"',
            '"--devices=#{d.blk_device.name}", env: enroll_env)',
        )
        missing_initial_tpm_prediction = [
            snippet
            for snippet in required_initial_tpm_prediction
            if snippet not in bls_source
        ]
        if missing_initial_tpm_prediction:
            raise RuntimeError(
                "installer TPM2 enrollment initial prediction invariant missing: "
                + repr(missing_initial_tpm_prediction)
            )

        systemdboot_source = (
            inst / "usr/share/YaST2/lib/bootloader/systemdboot.rb"
        ).read_text()
        if "--portable" in bls_source or "portable:" in systemdboot_source:
            raise RuntimeError(
                "sdbootutil portable layout is forbidden: keep stock /EFI/systemd "
                "assets and rely on update_nvram=false to suppress firmware writes"
            )
        if 'Yast::Execute.on_target!(SDBOOTUTIL, "install")' not in bls_source:
            raise RuntimeError(
                "stock sdbootutil install path missing from BLS installer"
            )

        actual = {
            relative: sha256(inst / relative)
            for relative in POST_PATCH_HASHES
        }
        mismatches = {
            relative: {
                "expected": POST_PATCH_HASHES[relative],
                "actual": actual[relative],
            }
            for relative in POST_PATCH_HASHES
            if actual[relative] != POST_PATCH_HASHES[relative]
        }
        if mismatches:
            raise RuntimeError(
                "post-patch Snapshot installer identity mismatch: "
                + json.dumps(mismatches, sort_keys=True)
            )

        return {
            "patches": {name: digest for name, _, digest in patches},
            "post_patch_hashes": actual,
        }


def _write_layer_manifests(build_root):
    symlinks = []
    files = []

    for path in sorted(build_root.rglob("*")):
        relative = path.relative_to(build_root).as_posix()
        if path.is_symlink():
            symlinks.append(f"./{relative} -> {os.readlink(path)}")
        elif path.is_file() and relative != "SHA256SUMS":
            files.append(f"{sha256(path)}  ./{relative}")

    (build_root / "SYMLINKS").write_text(
        ("\n".join(symlinks) + "\n") if symlinks else ""
    )

    # Include the symlink inventory itself in the exhaustive regular-file hash list.
    manifest_entries = []
    for path in sorted(build_root.rglob("*")):
        relative = path.relative_to(build_root).as_posix()
        if path.is_symlink() or not path.is_file() or relative == "SHA256SUMS":
            continue
        manifest_entries.append(f"{sha256(path)}  ./{relative}")
    (build_root / "SHA256SUMS").write_text("\n".join(manifest_entries) + "\n")


def _verify_layer_policy(root):
    root = Path(root)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    update_files = {
        name for name in actual_files
        if name.startswith("linux/suse/x86_64-tw/inst-sys/.update.")
    }
    if len(update_files) != 1:
        raise RuntimeError(
            "OEMDRV policy requires exactly one DUD update marker, got "
            + repr(sorted(update_files))
        )
    marker = next(iter(update_files))
    suffix = marker.rsplit(".update.", 1)[1]
    if len(suffix) != 16 or any(ch not in "0123456789abcdef" for ch in suffix):
        raise RuntimeError(f"invalid DUD update marker identity: {marker}")

    expected_files = set(OEMDRV_STATIC_FILES) | {marker}
    if actual_files != expected_files:
        raise RuntimeError(
            "OEMDRV file policy mismatch: "
            f"missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )

    actual_symlinks = {
        path.relative_to(root).as_posix(): os.readlink(path)
        for path in root.rglob("*")
        if path.is_symlink()
    }
    if actual_symlinks != OEMDRV_SYMLINKS:
        raise RuntimeError(
            "OEMDRV symlink policy mismatch: "
            f"expected={OEMDRV_SYMLINKS}, actual={actual_symlinks}"
        )


def _verify_layer_tree(root):
    root = Path(root)
    _verify_layer_policy(root)
    manifest = root / "SHA256SUMS"
    symlink_manifest = root / "SYMLINKS"
    if not manifest.is_file() or not symlink_manifest.is_file():
        raise RuntimeError("OEMDRV verification manifests are missing")

    expected_files = {}
    for line in manifest.read_text().splitlines():
        if not line:
            continue
        digest, relative = line.split("  ./", 1)
        expected_files[relative] = digest

    actual_files = {}
    actual_symlinks = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            actual_symlinks[relative] = os.readlink(path)
        elif path.is_file() and relative != "SHA256SUMS":
            actual_files[relative] = sha256(path)

    if actual_files != expected_files:
        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))
        changed = sorted(
            name for name in set(actual_files) & set(expected_files)
            if actual_files[name] != expected_files[name]
        )
        raise RuntimeError(
            "OEMDRV regular-file manifest verification failed: "
            f"missing={missing}, extra={extra}, changed={changed}"
        )

    expected_symlinks = {}
    for line in symlink_manifest.read_text().splitlines():
        if not line:
            continue
        left, target = line.split(" -> ", 1)
        expected_symlinks[left.removeprefix("./")] = target

    if actual_symlinks != expected_symlinks:
        raise RuntimeError(
            "OEMDRV symlink manifest verification failed: "
            f"expected={expected_symlinks}, actual={actual_symlinks}"
        )


def _verify_oemdrv_iso(iso, xorriso, xorriso_lib):
    import tempfile

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(xorriso_lib)
    with tempfile.TemporaryDirectory(prefix="oemdrv-readback-") as td:
        root = Path(td)
        subprocess.run(
            [
                str(xorriso), "-osirrox", "on",
                "-indev", str(iso),
                "-extract", "/", str(root),
            ],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _verify_layer_tree(root)


def build_oemdrv(
    cfg=None,
    *,
    credentials_override=None,
    output_dir=None,
    artifact_prefix="oemdrv",
    vm_observability=True,
    build_flavor="vmbench",
    target_device=None,
):
    cfg = cfg or Config()
    ET.parse(cfg.profile)
    if target_device is None:
        if build_flavor == "release":
            raise RuntimeError(
                "release build requires an explicit persistent target device"
            )
        target_device = cfg.vm_target_device
    if not isinstance(target_device, str) or not target_device.startswith("/dev/disk/by-id/"):
        raise RuntimeError(
            "target device must be a persistent /dev/disk/by-id/... path"
        )
    credentials = (
        load_credentials(cfg)
        if credentials_override is None
        else dict(credentials_override)
    )

    source = _verified_snapshot_source(cfg)
    patches = _patchset(cfg)
    profile_sha = sha256(cfg.profile)
    patchset_material = "\n".join(
        f"{name}={digest}" for name, _, digest in patches
    )
    patch_sha = hashlib.sha256(patchset_material.encode()).hexdigest()

    cred_stat = (
        cfg.credentials.stat()
        if credentials_override is None and cfg.credentials.exists()
        else None
    )
    credential_source_stamp = (
        f"vm-file:{cred_stat.st_mtime_ns}:{cred_stat.st_size}"
        if cred_stat is not None
        else "explicit-credential-set"
    )
    opaque_input = (
        f"{profile_sha}\n{patch_sha}\n"
        f"{build_flavor}\n{credential_source_stamp}\n"
        f"{time.time_ns()}\n"
    )
    ident = hashlib.sha256(opaque_input.encode()).hexdigest()[:16]

    xorriso = cfg.cache / "tools/rootless/xorriso/usr/bin/xorriso"
    xorriso_lib = cfg.cache / (
        "tools/rootless/xorriso/usr/lib/x86_64-linux-gnu"
    )

    output_dir = Path(output_dir) if output_dir is not None else cfg.bench
    output_dir.mkdir(parents=True, exist_ok=True)
    build_root = output_dir / f"{artifact_prefix}-root-{ident}"
    iso = output_dir / f"{artifact_prefix}-{ident}.iso"

    if build_root.exists():
        shutil.rmtree(build_root)
    build_root.mkdir(parents=True)

    credential_mode = render_runtime_profile(
        cfg,
        build_root / "autoinst.xml",
        credentials,
        vm_observability=vm_observability,
        target_device=target_device,
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
        f"UpdateName:\tDesktop-Linux {build_flavor} {ident}\n"
    )

    (build_root / "BASE-ISO.sha256").write_text(
        "0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99  "
        "openSUSE-Tumbleweed-DVD-x86_64-Snapshot20260930-Media.iso\n"
    )
    source_identity = [
        "snapshot=Snapshot20260930",
        f"official-iso-sha256={SNAPSHOT_ISO_SHA256}",
        "source-mode=verified-clean-instsys-files",
        f"build-flavor={build_flavor}",
        f"vm-observability={'yes' if vm_observability else 'no'}",
        f"target-device={target_device}",
        f"profile-sha256={profile_sha}",
        f"patchset-sha256={patch_sha}",
    ]
    source_identity.extend(
        f"rpm={rpm_path}" for rpm_path in SNAPSHOT_RPM_INPUTS
    )
    source_identity.extend(
        f"stock:{relative}={digest}"
        for relative, digest in SNAPSHOT_SOURCE_HASHES.items()
    )
    source_identity.extend(patchset_material.splitlines())
    (build_root / "SOURCE-IDENTITY.txt").write_text(
        "\n".join(source_identity) + "\n"
    )

    _write_layer_manifests(build_root)

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
    _verify_oemdrv_iso(iso, xorriso, xorriso_lib)
    iso_sha = sha256(iso)
    shutil.rmtree(build_root)

    (output_dir / "current-oem.path").write_text(str(iso) + "\n")
    (output_dir / "current-build.txt").write_text(
        f"PROFILE_SHA={profile_sha}\n"
        f"PATCHSET_SHA={patch_sha}\n"
        + "".join(
            f"{name.upper()}_SHA={digest}\n"
            for name, _, digest in patches
        )
        + f"ID={ident}\n"
        f"ISO={iso}\n"
        f"ISO_SHA256={iso_sha}\n"
        f"TARGET_DEVICE={target_device}\n"
        f"EMBEDDED={','.join(credential_mode['embedded'])}\n"
        f"MISSING={','.join(credential_mode['missing'])}\n"
    )

    for stale in output_dir.glob(f"{artifact_prefix}-*.iso"):
        if stale != iso:
            stale.unlink()

    return {
        "id": ident,
        "iso": iso,
        "iso_sha": iso_sha,
        "profile_sha": profile_sha,
        "patch_sha": patch_sha,
        "patches": {name: digest for name, _, digest in patches},
        "credentials": credential_mode,
    }


def build_release_oemdrv(target_device, cfg=None):
    cfg = cfg or Config()
    if target_device == cfg.vm_target_device:
        raise RuntimeError("release target must not use the VM proof device identifier")
    release_dir = cfg.cache / "release"
    result = build_oemdrv(
        cfg,
        credentials_override={},
        output_dir=release_dir,
        artifact_prefix="desktop-linux-release-oemdrv",
        vm_observability=False,
        build_flavor="release",
        target_device=target_device,
    )

    mode = result["credentials"]
    if mode["embedded"]:
        raise RuntimeError(
            "release OEMDRV must not embed installer credentials: "
            + repr(mode["embedded"])
        )
    if sorted(mode["missing"]) != ["pin", "recovery", "root"]:
        raise RuntimeError(
            "release OEMDRV must retain all native credential asks: "
            + repr(mode["missing"])
        )
    return result
