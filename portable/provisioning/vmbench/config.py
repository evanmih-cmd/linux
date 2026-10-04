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
    def vm_target_device(self):
        return "/dev/disk/by-id/ata-PORTABLE_WORKSTATION_SSD_PORTABLETARGET000001"

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

    @property
    def update_nvram_patch(self):
        return self.repo / (
            "portable/provisioning/"
            "systemd-boot-update-nvram.patch"
        )

    @property
    def network_patch(self):
        return self.repo / (
            "portable/provisioning/"
            "networkmanager-offline-write.patch"
        )

    @property
    def portable_layout_patch(self):
        return self.repo / (
            "portable/provisioning/"
            "systemd-boot-portable-layout.patch"
        )

    @property
    def snapshot_instsys_source(self):
        return self.cache / "tools/snapshot20260930-instsys-source"
