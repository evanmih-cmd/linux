from dataclasses import dataclass
from pathlib import Path
import os


ISO_SHA256 = "bd4307df32bc8af33b39ccecb1174aeb345386630f89a2b86c7a4e36b55ea650"


@dataclass(frozen=True)
class Config:
    """Configuration for the disposable Windows 11 Pro VirtualBox bench."""

    repo: Path = Path(__file__).resolve().parents[3]
    cache: Path = Path(
        os.environ.get("DESKTOP_WINDOWS_CACHE", "~/.cache/desktop-windows")
    ).expanduser()
    ws_url: str = os.environ.get(
        "VBOX_WS_URL", "http://172.30.80.1:18083/"
    )
    vm_name: str = os.environ.get(
        "DESKTOP_WINDOWS_VM", "Desktop-Windows-11-Pro"
    )
    vm_vcpus: int = int(os.environ.get("DESKTOP_WINDOWS_VM_VCPUS", "4"))
    vm_memory_mib: int = int(
        os.environ.get("DESKTOP_WINDOWS_VM_MEMORY_MIB", "8192")
    )
    vm_disk_gib: int = int(
        os.environ.get("DESKTOP_WINDOWS_VM_DISK_GIB", "96")
    )
    vm_graphics_controller: str = os.environ.get(
        "DESKTOP_WINDOWS_VM_GRAPHICS_CONTROLLER", "VBoxSVGA"
    )
    vm_vram_mib: int = int(
        os.environ.get("DESKTOP_WINDOWS_VM_VRAM_MIB", "128")
    )
    vm_accel3d: bool = (
        os.environ.get("DESKTOP_WINDOWS_VM_ACCEL3D", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    vm_keyboard_hid: str = os.environ.get(
        "DESKTOP_WINDOWS_VM_KEYBOARD_HID", "USBKeyboard"
    )
    vm_nested_hwvirt: bool = (
        os.environ.get("DESKTOP_WINDOWS_VM_NESTED_HWVIRT", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    keep_runs: int = int(
        os.environ.get("DESKTOP_WINDOWS_KEEP_RUNS", "8")
    )
    install_timeout_minutes: int = int(
        os.environ.get("DESKTOP_WINDOWS_INSTALL_TIMEOUT_MINUTES", "75")
    )
    install_stall_minutes: int = int(
        os.environ.get("DESKTOP_WINDOWS_INSTALL_STALL_MINUTES", "5")
    )

    @property
    def bench(self) -> Path:
        return self.cache / "vbox-bench"

    @property
    def runs(self) -> Path:
        return self.bench / "runs"

    @property
    def vm_disk(self) -> Path:
        return self.bench / "windows11-pro.vdi"

    @property
    def official_iso(self) -> Path:
        return Path(
            os.environ.get(
                "DESKTOP_WINDOWS_ISO",
                "/home/github-runner/Windows11_Client_x64_en-us_26300_9457.iso",
            )
        ).expanduser()

    @property
    def official_iso_sha256(self) -> str:
        return ISO_SHA256

    @property
    def credentials(self) -> Path:
        return Path(
            os.environ.get(
                "DESKTOP_WINDOWS_VM_CREDENTIALS",
                str(self.bench / "credentials.json"),
            )
        ).expanduser()

    @property
    def guest_user(self) -> str:
        return os.environ.get("DESKTOP_WINDOWS_VM_USER", "vmbench")

    @property
    def guest_full_name(self) -> str:
        return "Desktop Windows VM Bench"

    @property
    def guest_hostname(self) -> str:
        return "winbench"

    @property
    def guest_timezone(self) -> str:
        return os.environ.get(
            "DESKTOP_WINDOWS_VM_TIMEZONE", "W. Europe Standard Time"
        )

    @property
    def payload(self) -> Path:
        return self.repo / "windows/vm/payload"

    @property
    def audit_script(self) -> Path:
        return self.payload / "audit.ps1"

    @property
    def workstation_configuration(self) -> Path:
        return self.repo / "windows/configuration/workstation.winget"

    @property
    def configuration_launcher(self) -> Path:
        return self.payload / "apply-configuration.ps1"

    @property
    def guest_work_dir(self) -> str:
        return r"C:\ProgramData\DesktopWindows"

    @property
    def guest_audit_path(self) -> str:
        return self.guest_work_dir + r"\audit.json"

    @property
    def xorriso(self) -> Path:
        return (
            Path(
                os.environ.get(
                    "DESKTOP_WINDOWS_XORRISO",
                    "~/.cache/desktop-linux/tools/rootless/xorriso/usr/bin/xorriso",
                )
            ).expanduser()
        )

    @property
    def xorriso_lib(self) -> Path:
        return (
            Path(
                os.environ.get(
                    "DESKTOP_WINDOWS_XORRISO_LIB",
                    "~/.cache/desktop-linux/tools/rootless/xorriso/usr/lib/x86_64-linux-gnu",
                )
            ).expanduser()
        )
