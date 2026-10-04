import hashlib
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

from config import Config


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for chunk in iter(lambda: src.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_oemdrv(cfg=None):
    cfg = cfg or Config()
    ET.parse(cfg.profile)

    profile_sha = sha256(cfg.profile)
    patch_sha = sha256(cfg.planner_patch)
    ident = hashlib.sha256(
        f"{profile_sha}\n{patch_sha}\n".encode()
    ).hexdigest()[:16]

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

    if not iso.exists():
        if build_root.exists():
            shutil.rmtree(build_root)
        shutil.copytree(base, build_root, symlinks=True)
        shutil.copy2(cfg.profile, build_root / "autoinst.xml")

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
    )

    old = sorted(
        cfg.bench.glob("oemdrv-*.iso"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in old[3:]:
        stale.unlink()

    return {
        "id": ident,
        "iso": iso,
        "profile_sha": profile_sha,
        "patch_sha": patch_sha,
    }
