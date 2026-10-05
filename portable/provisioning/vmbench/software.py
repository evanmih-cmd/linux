import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from config import Config


YAST_NS = "http://www.suse.com/1.0/yast2ns"
CONFIG_NS = "http://www.suse.com/1.0/configns"
ET.register_namespace("", YAST_NS)
ET.register_namespace("config", CONFIG_NS)


class SoftwareBaselineError(RuntimeError):
    pass


def _q(name):
    return f"{{{YAST_NS}}}{name}"


def _child(parent, name):
    return parent.find(_q(name))


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for chunk in iter(lambda: src.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_software_manifest(cfg=None):
    cfg = cfg or Config()
    data = json.loads(cfg.software_manifest.read_text())
    if data.get("schema") != 1:
        raise SoftwareBaselineError(
            f"unsupported software manifest schema: {data.get('schema')!r}"
        )
    return data


def _asset(cfg, relative):
    return cfg.repo / relative


def validate_manifest_assets(cfg=None, manifest=None):
    cfg = cfg or Config()
    manifest = manifest or load_software_manifest(cfg)
    checks = (
        manifest["ledger_udev"],
        manifest["browser_policy"],
    )
    for item in checks:
        path = _asset(cfg, item["asset_path"])
        if not path.is_file():
            raise SoftwareBaselineError(f"missing software asset: {path}")
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise SoftwareBaselineError(
                f"software asset hash mismatch for {path}: "
                f"{actual} != {item['sha256']}"
            )


def _texts(parent, child_name):
    if parent is None:
        return []
    return [(node.text or "").strip() for node in parent.findall(_q(child_name))]


def _bool_text(node):
    if node is None:
        return None
    value = (node.text or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise SoftwareBaselineError(f"invalid AutoYaST boolean: {value!r}")


def _listentry_state(entry):
    state = {}
    for name in (
        "media_url",
        "product_dir",
        "alias",
        "name",
        "priority",
        "ask_on_error",
        "confirm_license",
    ):
        node = _child(entry, name)
        if node is None:
            continue
        text = (node.text or "").strip()
        if name == "priority":
            state[name] = int(text)
        elif name in ("ask_on_error", "confirm_license"):
            state[name] = _bool_text(node)
        else:
            state[name] = text

    sig = _child(entry, "signature-handling")
    keyids = []
    if sig is not None:
        for bool_name in (
            "accept_unsigned_file",
            "accept_file_without_checksum",
            "accept_verification_failed",
        ):
            node = _child(sig, bool_name)
            if node is not None:
                state[bool_name] = _bool_text(node)

        key_blocks = ("accept_unknown_gpg_key", "import_gpg_key")
        present = [_child(sig, name) is not None for name in key_blocks]
        if any(present) and not all(present):
            raise SoftwareBaselineError(
                "accept/import GPG key handling must be configured together"
            )
        if all(present):
            for block_name in key_blocks:
                block = _child(sig, block_name)
                all_node = _child(block, "all")
                if _bool_text(all_node):
                    raise SoftwareBaselineError(
                        "software add-on must never accept/import all unknown GPG keys"
                    )
                keys = _child(block, "keys")
                ids = _texts(keys, "keyid")
                if not ids:
                    raise SoftwareBaselineError(
                        f"signature handling {block_name} has no pinned key IDs"
                    )
                if keyids and ids != keyids:
                    raise SoftwareBaselineError(
                        "accept/import GPG key lists differ"
                    )
                keyids = ids
    if keyids:
        state["signature_keyids"] = keyids
    return state


def profile_software_state(profile_path):
    root = ET.parse(profile_path).getroot()
    software = _child(root, "software")
    if software is None:
        raise SoftwareBaselineError("AutoYaST profile has no <software> section")
    patterns = _child(software, "patterns")
    packages = _child(software, "packages")

    add_on = _child(root, "add-on")
    repos = []
    if add_on is not None:
        others = _child(add_on, "add_on_others")
        if others is not None:
            repos = [_listentry_state(entry) for entry in others.findall(_q("listentry"))]
        products = _child(add_on, "add_on_products")
        if products is not None and list(products):
            raise SoftwareBaselineError(
                "software baseline permits add_on_others only, not add_on_products"
            )

    files = {}
    files_node = _child(root, "files")
    if files_node is not None:
        for entry in files_node.findall(_q("file")):
            path = (_child(entry, "file_path").text or "").strip()
            files[path] = {
                "owner": (_child(entry, "file_owner").text or "").strip(),
                "permissions": (
                    _child(entry, "file_permissions").text or ""
                ).strip(),
                "contents": _child(entry, "file_contents").text or "",
            }

    return {
        "patterns": _texts(patterns, "pattern"),
        "packages": _texts(packages, "package"),
        "do_online_update": _bool_text(_child(software, "do_online_update")),
        "install_recommended": _bool_text(
            _child(software, "install_recommended")
        ),
        "repositories": repos,
        "files": files,
    }


def expected_software_state(cfg=None, manifest=None):
    cfg = cfg or Config()
    manifest = manifest or load_software_manifest(cfg)
    expected_files = {}
    for item in (manifest["ledger_udev"], manifest["browser_policy"]):
        source = _asset(cfg, item["asset_path"])
        expected_files[item["install_path"]] = {
            "owner": item["owner"],
            "permissions": item["permissions"],
            "contents": source.read_text(),
        }
    return {
        "patterns": manifest["patterns"],
        "packages": manifest["packages"],
        "do_online_update": manifest["software"]["do_online_update"],
        "install_recommended": manifest["software"]["install_recommended"],
        "repositories": manifest["add_on_repositories"],
        "files": expected_files,
    }


def validate_software_profile(profile_path, cfg=None, manifest=None):
    cfg = cfg or Config()
    manifest = manifest or load_software_manifest(cfg)
    validate_manifest_assets(cfg, manifest)
    actual = profile_software_state(profile_path)
    expected = expected_software_state(cfg, manifest)
    if actual != expected:
        raise SoftwareBaselineError(
            "AutoYaST software contract mismatch:\n"
            + json.dumps(
                {"expected": expected, "actual": actual},
                indent=2,
                sort_keys=True,
            )
        )
    return actual


def _download(url, destination, expected_sha=None):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    actual = sha256_bytes(data)
    if expected_sha is not None and actual != expected_sha:
        raise SoftwareBaselineError(
            f"download hash mismatch for {url}: {actual} != {expected_sha}"
        )
    destination.write_bytes(data)
    return actual


def _metadata_locations_and_checksums(repomd_path):
    root = ET.parse(repomd_path).getroot()
    ns = {"repo": "http://linux.duke.edu/metadata/repo"}
    out = []
    for data in root.findall("repo:data", ns):
        location = data.find("repo:location", ns)
        checksum = data.find("repo:checksum", ns)
        if location is None or checksum is None:
            raise SoftwareBaselineError("repomd data entry lacks location/checksum")
        out.append(
            (
                location.attrib["href"],
                checksum.attrib["type"],
                (checksum.text or "").strip(),
            )
        )
    return out


def _digest_with_algorithm(data, algorithm):
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise SoftwareBaselineError(
            f"unsupported repository checksum algorithm {algorithm!r}"
        ) from exc
    digest.update(data)
    return digest.hexdigest()


def _download_repo_metadata(base_url, destination, repomd_sha):
    destination = Path(destination)
    repodata = destination / "repodata"
    repomd = repodata / "repomd.xml"
    _download(base_url + "repodata/repomd.xml", repomd, repomd_sha)
    _download(base_url + "repodata/repomd.xml.asc", repodata / "repomd.xml.asc")
    _download(base_url + "repodata/repomd.xml.key", repodata / "repomd.xml.key")

    for relative, algorithm, expected in _metadata_locations_and_checksums(repomd):
        with urllib.request.urlopen(base_url + relative, timeout=120) as response:
            data = response.read()
        actual = _digest_with_algorithm(data, algorithm)
        if actual != expected:
            raise SoftwareBaselineError(
                f"signed repository metadata checksum mismatch for {relative}: "
                f"{actual} != {expected}"
            )
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _verify_opensuse_rpm_signatures(target, cfg, manifest):
    target = Path(target)
    dvd = _ensure_dvd_extracted(cfg)
    command = """
set -e
rpm --root /tmp/rpmroot --initdb
rpm --root /tmp/rpmroot --import /dvd/repodata/repomd.xml.key
for p in /repo/*/*.rpm; do
    rpm --root /tmp/rpmroot --checksig "$p" | grep -q "signatures OK"
done
"""
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{dvd}:/dvd:ro",
            "-v",
            f"{target}:/repo:ro",
            manifest["build_tool"]["docker_image"],
            "bash",
            "-lc",
            command,
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode != 0:
        raise SoftwareBaselineError(
            "openSUSE RPM signature verification failed:\n"
            + proc.stdout[-20000:]
        )


def _mirror_opensuse(root, manifest, cfg=None):
    cfg_obj = cfg or Config()
    source = manifest["opensuse_history"]
    target = Path(root) / "opensuse"
    target.mkdir(parents=True, exist_ok=True)
    for relative, digest in sorted(source["rpms"].items()):
        _download(source["base_url"] + relative, target / relative, digest)

    # Intentionally no repodata. libzypp auto-detects a directory of signed
    # RPMs as a plaindir repository. This keeps the add-on self-consistent:
    # it can never advertise a package that is not physically present.
    if (target / "repodata").exists():
        raise SoftwareBaselineError("openSUSE plaindir must not contain repodata")
    _verify_opensuse_rpm_signatures(target, cfg_obj, manifest)


def _mirror_google(root, manifest):
    cfg = manifest["google_chrome"]
    target = Path(root) / "google"
    for relative, digest in sorted(cfg["files"].items()):
        _download(cfg["base_url"] + relative, target / relative, digest)
    _download(
        cfg["signing_key_url"],
        target / "repodata/repomd.xml.key",
        cfg["signing_key_sha256"],
    )
    _verify_google_repo_signature(target, cfg)


def _verify_google_repo_signature(target, cfg):
    target = Path(target)
    key = target / "repodata/repomd.xml.key"
    signature = target / "repodata/repomd.xml.asc"
    repomd = target / "repodata/repomd.xml"
    with tempfile.TemporaryDirectory(prefix="google-gpg-") as td:
        homedir = Path(td)
        homedir.chmod(0o700)
        subprocess.run(
            [
                "gpg",
                "--batch",
                "--homedir",
                str(homedir),
                "--import",
                str(key),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        verified = subprocess.run(
            [
                "gpg",
                "--batch",
                "--homedir",
                str(homedir),
                "--status-fd=1",
                "--verify",
                str(signature),
                str(repomd),
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    valid = None
    for line in verified.stdout.splitlines():
        if line.startswith("[GNUPG:] VALIDSIG "):
            valid = line.split()
            break
    if not valid:
        raise SoftwareBaselineError(
            "Google repomd signature verification produced no VALIDSIG"
        )

    signing_fingerprint = valid[2]
    primary_fingerprint = valid[-1]
    expected_primary = cfg["signing_key_fingerprint"].upper()
    expected_signing_keyid = cfg["repomd_signature_keyid"].upper()

    if primary_fingerprint.upper() != expected_primary:
        raise SoftwareBaselineError(
            "Google signing primary fingerprint mismatch: "
            f"{primary_fingerprint} != {expected_primary}"
        )
    if not signing_fingerprint.upper().endswith(expected_signing_keyid):
        raise SoftwareBaselineError(
            "Google repomd signing subkey mismatch: "
            f"{signing_fingerprint} does not end with {expected_signing_keyid}"
        )

def _copy_assets(root, cfg, manifest):
    assets = Path(root) / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for item in (manifest["ledger_udev"], manifest["browser_policy"]):
        source = _asset(cfg, item["asset_path"])
        shutil.copy2(source, assets / source.name)


def _write_tree_manifest(root):
    root = Path(root)
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            rows.append(
                f"{sha256_file(path)}  ./{path.relative_to(root).as_posix()}"
            )
    (root / "SHA256SUMS").write_text("\n".join(rows) + "\n")


def _verify_tree_manifest(root):
    root = Path(root)
    expected = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, relative = line.split("  ./", 1)
        expected[relative] = digest
    actual = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            actual[path.relative_to(root).as_posix()] = sha256_file(path)
    if actual != expected:
        raise SoftwareBaselineError(
            "software media file manifest mismatch: "
            f"missing={sorted(set(expected)-set(actual))}, "
            f"extra={sorted(set(actual)-set(expected))}, "
            f"changed={sorted(k for k in set(actual)&set(expected) if actual[k] != expected[k])}"
        )


def _xorriso_env(cfg):
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(cfg.xorriso_lib)
    return env


def _ensure_dvd_extracted(cfg):
    if not cfg.official_iso.is_file():
        raise SoftwareBaselineError(f"missing official ISO: {cfg.official_iso}")
    if sha256_file(cfg.official_iso) != cfg.official_iso_sha256:
        raise SoftwareBaselineError("official Snapshot ISO hash mismatch")
    root = cfg.extracted_official_iso
    if (root / "repodata/repomd.xml").is_file():
        return root
    temp = root.with_name(root.name + ".tmp")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    subprocess.run(
        [
            str(cfg.xorriso),
            "-osirrox",
            "on",
            "-indev",
            str(cfg.official_iso),
            "-extract",
            "/",
            str(temp),
        ],
        env=_xorriso_env(cfg),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if root.exists():
        shutil.rmtree(root)
    temp.rename(root)
    return root


def _solver_command(manifest):
    patterns = " ".join(manifest["patterns"])
    packages = " ".join(manifest["packages"])
    return f"""
set -e
rpm --root /rootfs --initdb
zypper --root /rootfs -n ar -p 10 dir:/dvd dvd
zypper --root /rootfs -n ar -p 20 dir:/media/google google
zypper --root /rootfs -n ar -p 30 dir:/media/opensuse opensuse
zypper --root /rootfs --gpg-auto-import-keys -n refresh
zypper --root /rootfs -n install --download-only --recommends -t pattern {patterns}
zypper --root /rootfs -n install --download-only --recommends {packages}
echo OFFLINE_SOFTWARE_RESOLVE_PASS
"""


def verify_offline_software_tree(root, cfg=None, manifest=None):
    cfg = cfg or Config()
    manifest = manifest or load_software_manifest(cfg)
    dvd = _ensure_dvd_extracted(cfg)
    with tempfile.TemporaryDirectory(
        prefix="software-resolve-", dir=cfg.software_media_dir
    ) as td:
        rootfs = Path(td) / "rootfs"
        rootfs.mkdir()
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{rootfs}:/rootfs",
            "-v",
            f"{dvd}:/dvd:ro",
            "-v",
            f"{Path(root)}:/media:ro",
            manifest["build_tool"]["docker_image"],
            "bash",
            "-lc",
            _solver_command(manifest),
        ]
        proc = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if proc.returncode != 0 or "OFFLINE_SOFTWARE_RESOLVE_PASS" not in proc.stdout:
            raise SoftwareBaselineError(
                "offline software solver proof failed:\n" + proc.stdout[-20000:]
            )
        return {
            "status": "PASS",
            "marker": "OFFLINE_SOFTWARE_RESOLVE_PASS",
        }



def _verify_local_repo_locations(repo_root, manifest=None):
    repo_root = Path(repo_root)
    manifest = manifest or load_software_manifest(Config())

    if (repo_root / "repodata").exists():
        raise SoftwareBaselineError(
            "openSUSE software overlay must be plaindir: repodata is forbidden"
        )

    rpm_files = {
        path.relative_to(repo_root).as_posix()
        for path in repo_root.rglob("*.rpm")
    }
    expected = set(manifest["opensuse_history"]["rpms"])
    if rpm_files != expected:
        raise SoftwareBaselineError(
            "openSUSE plaindir file mismatch: "
            f"missing={sorted(expected - rpm_files)}, "
            f"extra={sorted(rpm_files - expected)}"
        )

    return {
        "packages": len(rpm_files),
        "locations": sorted(rpm_files),
    }


def verify_software_payload_tree(root):
    root = Path(root)
    _verify_tree_manifest(root)
    return _verify_local_repo_locations(root / "opensuse")


def prepare_software_payload(cfg=None, *, force=False):
    """Build the folder tree copied into /portable on the Desktop-Linux layer."""
    cfg = cfg or Config()
    manifest = load_software_manifest(cfg)
    validate_manifest_assets(cfg, manifest)
    cfg.software_media_dir.mkdir(parents=True, exist_ok=True)

    manifest_sha = sha256_file(cfg.software_manifest)
    ident = manifest_sha[:16]
    target = cfg.software_media_dir / f"payload-{ident}"

    if not force and target.is_dir():
        try:
            verify_software_payload_tree(target)
            return {
                "id": ident,
                "path": target,
                "manifest_sha": manifest_sha,
                "cached": True,
            }
        except Exception:
            shutil.rmtree(target)

    with tempfile.TemporaryDirectory(
        prefix="software-payload-build-", dir=cfg.software_media_dir
    ) as td:
        root = Path(td) / "root"
        root.mkdir()
        _mirror_opensuse(root, manifest)
        _mirror_google(root, manifest)
        _copy_assets(root, cfg, manifest)

        source_identity = {
            "manifest_sha256": manifest_sha,
            "snapshot": manifest["snapshot"],
            "official_iso_sha256": cfg.official_iso_sha256,
            "chrome_version": manifest["google_chrome"]["version"],
            "ledger_commit": manifest["ledger_udev"]["commit"],
            "docker_image": manifest["build_tool"]["docker_image"],
        }
        (root / "SOURCE-IDENTITY.json").write_text(
            json.dumps(source_identity, indent=2, sort_keys=True) + "\n"
        )

        solver = verify_offline_software_tree(root, cfg, manifest)
        (root / "OFFLINE-SOLVER-PROOF.json").write_text(
            json.dumps(solver, indent=2, sort_keys=True) + "\n"
        )
        _write_tree_manifest(root)
        verify_software_payload_tree(root)

        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(root, target)

    verify_software_payload_tree(target)
    return {
        "id": ident,
        "path": target,
        "manifest_sha": manifest_sha,
        "cached": False,
        "offline_solver": solver,
    }
