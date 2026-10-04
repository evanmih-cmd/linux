from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Config:
    repo: Path = Path(__file__).resolve().parents[3]
    cache: Path = Path(
        os.environ.get("DESKTOP_LINUX_CACHE", "~/.cache/desktop-linux")
    ).expanduser()
    ws_url: str = os.environ.get(
        "VBOX_WS_URL", "http://172.30.80.1:18083/"
    )
    vm_name: str = os.environ.get(
        "DESKTOP_LINUX_VM", "Desktop-Linux-TW"
    )
    target_size_gib: int = int(
        os.environ.get("DESKTOP_LINUX_TARGET_GIB", "48")
    )
    keep_runs: int = int(
        os.environ.get("DESKTOP_LINUX_KEEP_RUNS", "8")
    )

    @property
    def bench(self):
        return self.cache / "vbox-proof/bench"

    @property
    def runs(self):
        return self.bench / "runs"

    @property
    def credentials(self):
        return Path(os.environ.get(
            "DESKTOP_LINUX_VM_CREDENTIALS",
            str(self.bench / "credentials.json"),
        ))

    @property
    def guard(self):
        return self.cache / "vbox-proof/asus-internal-guard.vdi"

    @property
    def official_iso(self):
        return self.cache / (
            "tumbleweed-dvd/"
            "openSUSE-Tumbleweed-DVD-x86_64-"
            "Snapshot20260930-Media.iso"
        )

    @property
    def profile(self):
        return self.repo / "portable/provisioning/autoinst-vm-proof.xml"

    @property
    def auth_patch(self):
        return self.repo / (
            "portable/provisioning/"
            "systemd-fde-autoyast-authentication.patch"
        )
