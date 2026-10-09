import hashlib
import json
import os
import secrets
from pathlib import Path

from config import Config


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for chunk in iter(lambda: src.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_official_iso(cfg=None):
    cfg = cfg or Config()
    path = cfg.official_iso
    if not path.is_file():
        raise RuntimeError(f"Windows ISO is missing: {path}")
    actual = sha256(path)
    expected = cfg.official_iso_sha256.lower()
    if actual.lower() != expected:
        raise RuntimeError(
            "Windows ISO SHA-256 mismatch: "
            f"actual={actual} expected={expected}"
        )
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": actual,
        "verified": True,
    }


def _new_password():
    # VM-only throwaway account.  Persist it outside Git so reinstall/audit can
    # reconnect without embedding a stable password in source control.
    token = secrets.token_urlsafe(18).replace("-", "A").replace("_", "b")
    return f"VmBench-{token}!9aA"


def load_or_create_credentials(cfg=None):
    cfg = cfg or Config()
    path = cfg.credentials
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {
            "user": cfg.guest_user,
            "password": _new_password(),
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(path, flags, 0o600)
        try:
            with os.fdopen(fd, "w") as dst:
                json.dump(data, dst, indent=2)
                dst.write("\n")
        except Exception:
            path.unlink(missing_ok=True)
            raise

    if set(data) != {"user", "password"}:
        raise RuntimeError(
            f"unexpected VM credential fields in {path}: {sorted(data)}"
        )
    if data["user"] != cfg.guest_user:
        raise RuntimeError(
            f"VM credential user {data['user']!r} != {cfg.guest_user!r}"
        )
    if not data["password"]:
        raise RuntimeError("VM credential password is empty")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return data
