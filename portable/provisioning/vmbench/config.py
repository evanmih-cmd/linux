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
    vm_vcpus: int = int(
        os.environ.get("DESKTOP_LINUX_VM_VCPUS", "1")
    )
    vm_graphics_controller: str = os.environ.get(
        "DESKTOP_LINUX_VM_GRAPHICS_CONTROLLER", "VMSVGA"
    )
    vm_vram_mib: int = int(
        os.environ.get("DESKTOP_LINUX_VM_VRAM_MIB", "128")
    )
    vm_accel3d: bool = (
        os.environ.get("DESKTOP_LINUX_VM_ACCEL3D", "0").strip().lower()
        in {"1", "true", "yes", "on"}
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
    def vm_target_vdi(self):
        return self.bench / "target-software-baseline.vdi"

    @property
    def guard(self):
        return self.bench / "asus-internal-guard-proof.vdi"

    @property
    def guard_size_gib(self):
        return 16

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
    def software_manifest(self):
        return self.repo / "portable/provisioning/software-baseline.json"

    @property
    def software_media_dir(self):
        return self.cache / "software-media"

    @property
    def extracted_official_iso(self):
        return self.cache / "tumbleweed-dvd/extracted-20260930"

    @property
    def official_iso_sha256(self):
        return "0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99"

    @property
    def xorriso(self):
        return self.cache / "tools/rootless/xorriso/usr/bin/xorriso"

    @property
    def xorriso_lib(self):
        return self.cache / "tools/rootless/xorriso/usr/lib/x86_64-linux-gnu"

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
    def autoyast_schema(self):
        return self.cache / (
            "tools/rootless/yast2-schema/usr/share/YaST2/"
            "schema/autoyast/rng/profile.rng"
        )

    @property
    def xmllint(self):
        return self.cache / "tools/rootless/xmllint/root/usr/bin/xmllint"

    @property
    def snapshot_instsys_source(self):
        return self.cache / "tools/snapshot20260930-instsys-source"

    @property
    def official_iso_sha256(self):
        return "0ae329f1727aa4ca953b6f20f4b68906de55b66859a76a5d798e60f473f9db99"

    @property
    def extracted_official_iso(self):
        return self.cache / "tumbleweed-dvd/extracted-20260930"

    @property
    def software_manifest(self):
        return self.repo / "portable/provisioning/software-baseline.json"

    @property
    def software_media_dir(self):
        return self.cache / "software-media"

    @property
    def xorriso(self):
        return self.cache / "tools/rootless/xorriso/usr/bin/xorriso"

    @property
    def xorriso_lib(self):
        return self.cache / "tools/rootless/xorriso/usr/lib/x86_64-linux-gnu"
