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
if [ -r /download/vmbench-tpm2-pin ]; then
  if id="$(/usr/bin/keyctl search @u user sdbootutil-tpm2-pin 2>/dev/null)"; then
    /usr/bin/keyctl pupdate "$id" < /download/vmbench-tpm2-pin >/dev/null
  else
    /usr/bin/keyctl padd user sdbootutil-tpm2-pin @u       < /download/vmbench-tpm2-pin >/dev/null
  fi
fi
( sleep 2; printf 'VMBENCH_PROFILE_READY\n' > /dev/ttyS0 ) &
"""

    tree.write(destination, encoding="UTF-8", xml_declaration=True)

    missing = [key for key in ("recovery", "pin", "root") if key not in credentials]
    return {
        "embedded": embedded,
        "missing": missing,
    }


def build_oemdrv(cfg=None):
    cfg = cfg or Config()
    ET.parse(cfg.profile)
    credentials = load_credentials(cfg)

    profile_sha = sha256(cfg.profile)
    patch_sha = sha256(cfg.planner_patch)
    cred_stat = cfg.credentials.stat() if cfg.credentials.exists() else None
    opaque_input = (
        f"{profile_sha}\n{patch_sha}\n"
        f"{cred_stat.st_mtime_ns if cred_stat else 0}\n"
        f"{cred_stat.st_size if cred_stat else 0}\n"
        f"{time.time_ns()}\n"
    )
    ident = hashlib.sha256(opaque_input.encode()).hexdigest()[:16]

    base = cfg.cache / "layer/oemdrv-portable-root"
    exact = cfg.cache / (
        "tools/yast2-storage-ng-5.0.50-1.1/root/usr/share/"
        "YaST2/lib/y2storage/proposal/autoinst_drive_planner.rb"
    )
    xorriso = cfg.cache / "tools/rootless/xorriso/usr/bin/xorriso"
    xorriso_lib = cfg.cache / (
        "tools/rootless/xorriso/usr/lib/x86_64-linux-gnu"
    )

    cfg.bench.mkdir(parents=True, exist_ok=True)
    build_root = cfg.bench / f"oem-root-{ident}"
    iso = cfg.bench / f"oemdrv-{ident}.iso"

    if build_root.exists():
        shutil.rmtree(build_root)
    shutil.copytree(base, build_root, symlinks=True)

    credential_mode = render_runtime_profile(
        cfg,
        build_root / "autoinst.xml",
        credentials,
    )
    if "pin" in credentials:
        pin_file = build_root / "vmbench-tpm2-pin"
        pin_file.write_text(credentials["pin"])
        pin_file.chmod(0o600)

    inst = build_root / "linux/suse/x86_64-tw/inst-sys"
    planner_dir = inst / "usr/share/YaST2/lib/y2storage/proposal"
    planner_dir.mkdir(parents=True, exist_ok=True)
    planner = planner_dir / "autoinst_drive_planner.rb"
    shutil.copy2(exact, planner)

    with open(cfg.planner_patch, "rb") as patch:
        subprocess.run(
            ["patch", "--batch", "-p1"],
            cwd=inst,
            stdin=patch,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    orig = planner.with_suffix(planner.suffix + ".orig")
    if orig.exists():
        orig.unlink()

    for marker in inst.glob(".update.*"):
        marker.unlink()
    (inst / f".update.{ident}").touch()

    dud = build_root / "linux/suse/x86_64-tw/dud.config"
    dud.write_text(
        f"UpdateID:\t{ident}\n"
        "UpdateProduct:\topenSUSE Tumbleweed\n"
        "UpdateInstaller:\tyast\n"
        f"UpdateName:\tDesktop-Linux vmbench {ident}\n"
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
        f"PATCH_SHA={patch_sha}\n"
        f"ID={ident}\n"
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
        "credentials": credential_mode,
    }
