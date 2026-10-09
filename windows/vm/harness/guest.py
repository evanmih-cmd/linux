import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from machine import unc
from vbox import VBoxError


POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


class GuestInstallStall(RuntimeError):
    def __init__(self, heartbeat):
        self.heartbeat = heartbeat
        super().__init__(
            "guest install made no VDI progress while Guest Control "
            "was unavailable"
        )


class GuestControl:
    """VirtualBox Guest Control session backed by Guest Additions.

    This is the normal guest transport for the Windows bench.  No keyboard
    scancode command injection is used.
    """

    def __init__(self, box, user, password):
        self.box = box
        self.user = user
        self.password = password
        self.vbox_session = None
        self.guest_session = None

    def __enter__(self):
        try:
            self.vbox_session = self.box.lock("Shared")
            console = self.box.session_console(self.vbox_session)
            guest = self.box._vals(
                "IConsole_getGuest", [("_this", console)]
            )[0]
            self.guest_session = self.box._vals(
                "IGuest_createSession",
                [
                    ("_this", guest),
                    ("user", self.user),
                    ("password", self.password),
                    ("domain", ""),
                    ("sessionName", "desktop-windows-harness"),
                ],
            )[0]
            result = self.box._vals(
                "IGuestSession_waitForArray",
                [
                    ("_this", self.guest_session),
                    ("waitFor", "Start"),
                    ("timeoutMS", "30000"),
                ],
                timeout=40,
            )[0]
            if result not in ("Start", "Status"):
                raise VBoxError(f"guest session failed to start: {result}")
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc, tb):
        if self.guest_session:
            try:
                self.box._vals(
                    "IGuestSession_close", [("_this", self.guest_session)]
                )
            except Exception:
                pass
        if self.vbox_session:
            try:
                self.box.unlock(self.vbox_session)
            except Exception:
                pass

    def run(self, executable, args=(), timeout_ms=120000):
        pairs = [
            ("_this", self.guest_session),
            ("executable", executable),
        ]
        for arg in [executable, *args]:
            pairs.append(("arguments", arg))
        pairs.extend(
            [
                ("cwd", ""),
                ("flags", "Profile"),
                ("timeoutMS", str(timeout_ms)),
            ]
        )
        process = self.box._vals(
            "IGuestSession_processCreate", pairs, timeout=30
        )[0]
        # IGuestProcess extends IProcess in the VirtualBox API.  The
        # process lifecycle methods/properties are therefore exposed on the
        # IProcess SOAP interface, not IGuestProcess.  Poll status instead of
        # relying solely on waitForArray: VBox 7.2 WebService can report a
        # wait timeout even when status has already reached TerminatedNormally.
        deadline = time.monotonic() + (timeout_ms / 1000)
        status = None
        terminal = {
            "TerminatedNormally",
            "TerminatedSignal",
            "TerminatedAbnormally",
            "TimedOutKilled",
            "TimedOutAbnormally",
            "Down",
            "Error",
        }
        while time.monotonic() < deadline:
            status = self.box._vals(
                "IProcess_getStatus", [("_this", process)]
            )[0]
            if status in terminal:
                break
            time.sleep(0.2)
        else:
            raise VBoxError(
                "guest process did not reach a terminal state before timeout; "
                f"last_status={status!r}"
            )

        if status != "TerminatedNormally":
            raise VBoxError(
                f"guest process did not terminate normally: {status}"
            )
        code = int(
            self.box._vals(
                "IProcess_getExitCode", [("_this", process)]
            )[0]
        )
        if code != 0:
            raise VBoxError(
                f"guest process failed with exit code {code}: "
                f"{executable} {' '.join(args)}"
            )
        return code

    def run_capture(self, executable, args=(), timeout_ms=120000):
        pairs = [
            ("_this", self.guest_session),
            ("executable", executable),
        ]
        for arg in [executable, *args]:
            pairs.append(("arguments", arg))
        pairs.extend(
            [
                ("cwd", ""),
                ("flags", "Profile"),
                ("flags", "WaitForStdOut"),
                ("flags", "WaitForStdErr"),
                ("timeoutMS", str(timeout_ms)),
            ]
        )
        process = self.box._vals(
            "IGuestSession_processCreate", pairs, timeout=30
        )[0]

        import base64

        stdout = bytearray()
        stderr = bytearray()
        deadline = time.monotonic() + (timeout_ms / 1000)
        status = None
        terminal = {
            "TerminatedNormally",
            "TerminatedSignal",
            "TerminatedAbnormally",
            "TimedOutKilled",
            "TimedOutAbnormally",
            "Down",
            "Error",
        }

        while time.monotonic() < deadline:
            for handle, sink in ((1, stdout), (2, stderr)):
                response = self.box._raw(
                    "IProcess_read",
                    [
                        ("_this", process),
                        ("handle", str(handle)),
                        ("toRead", "65536"),
                        ("timeoutMS", "0"),
                    ],
                    timeout=5,
                )
                values = [
                    item.text or ""
                    for item in response.findall(".//returnval")
                ]
                if values and values[0]:
                    sink.extend(base64.b64decode(values[0]))

            status = self.box._vals(
                "IProcess_getStatus", [("_this", process)]
            )[0]
            if status in terminal:
                break
            time.sleep(0.2)
        else:
            raise VBoxError(
                "guest process did not reach a terminal state before timeout; "
                f"last_status={status!r}"
            )

        code = int(
            self.box._vals(
                "IProcess_getExitCode", [("_this", process)]
            )[0]
        )
        result = {
            "status": status,
            "exit_code": code,
            "stdout": stdout.decode("utf-8", "replace"),
            "stderr": stderr.decode("utf-8", "replace"),
        }
        if status != "TerminatedNormally" or code != 0:
            raise VBoxError(
                "guest process failed: "
                f"status={status} exit_code={code} "
                f"stderr={result['stderr']!r} stdout={result['stdout']!r}"
            )
        return result

    def powershell(self, command, timeout_ms=120000):
        return self.run(
            POWERSHELL,
            (
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ),
            timeout_ms=timeout_ms,
        )

    def ensure_directory(self, path):
        quoted = path.replace("'", "''")
        self.powershell(
            f"New-Item -ItemType Directory -Force -Path '{quoted}' "
            "| Out-Null"
        )

    def copy_to_guest(self, source, destination_dir):
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = str(PureWindowsPath(destination_dir) / source.name)
        progress = self.box._vals(
            "IGuestSession_fileCopyToGuest",
            [
                ("_this", self.guest_session),
                ("source", unc(source)),
                ("destination", destination),
            ],
        )[0]
        self.box.wait_progress_ok(
            progress, 120000, f"copy to guest: {source.name}"
        )
        return destination

    def copy_from_guest(self, source, destination_dir):
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / PureWindowsPath(source).name

        guest_file = self.box._vals(
            "IGuestSession_fileOpen",
            [
                ("_this", self.guest_session),
                ("path", source),
                ("accessMode", "ReadOnly"),
                ("openAction", "OpenExisting"),
                ("creationMode", "0"),
            ],
        )[0]
        try:
            remaining = int(
                self.box._vals(
                    "IFile_querySize", [("_this", guest_file)]
                )[0]
            )
            with destination.open("wb") as stream:
                while remaining:
                    to_read = min(1024 * 1024, remaining)
                    root = self.box._raw(
                        "IFile_read",
                        [
                            ("_this", guest_file),
                            ("toRead", str(to_read)),
                            ("timeoutMS", "30000"),
                        ],
                        timeout=40,
                    )
                    values = [
                        item.text or ""
                        for item in root.findall(".//returnval")
                    ]
                    if not values:
                        raise VBoxError(
                            f"guest file read returned no data: {source}"
                        )
                    chunk = base64.b64decode(values[0])
                    if not chunk:
                        raise VBoxError(
                            f"guest file read ended early: {source}"
                        )
                    stream.write(chunk)
                    remaining -= len(chunk)
            return destination
        finally:
            try:
                self.box._vals("IFile_close", [("_this", guest_file)])
            except Exception:
                pass


def wait_for_guest_additions(box, timeout_seconds=3600):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        try:
            last = box.guest_additions_run_level()
        except Exception:
            last = None
        if last in ("Userland", "Desktop"):
            return last
        time.sleep(5)
    raise TimeoutError(
        f"Guest Additions did not reach Userland/Desktop; last={last!r}"
    )


def wait_for_guest_control(
    cfg,
    timeout_seconds=3600,
    *,
    progress_path=None,
    stall_timeout_seconds=None,
):
    from config import Config
    from media import load_or_create_credentials
    from vbox import VBox

    cfg = cfg or Config()
    credentials = load_or_create_credentials(cfg)
    deadline = time.time() + timeout_seconds
    last_error = None
    last_level = None
    last_state = None
    last_vdi_mtime_ns = None
    last_vdi_change_at = time.time()

    def write_progress(guest_control=False):
        nonlocal last_vdi_mtime_ns, last_vdi_change_at
        disk = cfg.vm_disk
        disk_info = None
        if disk.is_file():
            stat = disk.stat()
            if last_vdi_mtime_ns != stat.st_mtime_ns:
                last_vdi_mtime_ns = stat.st_mtime_ns
                last_vdi_change_at = time.time()
            disk_info = {
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "seconds_since_change": round(
                    max(0.0, time.time() - last_vdi_change_at), 1
                ),
            }
        heartbeat = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "vm_state": last_state,
            "guest_additions_run_level": last_level,
            "guest_control": bool(guest_control),
            "last_error": last_error,
            "vdi": disk_info,
        }
        if progress_path is not None:
            Path(progress_path).write_text(
                json.dumps(heartbeat, indent=2, sort_keys=True) + "\n"
            )
        return heartbeat

    while time.time() < deadline:
        box = None
        try:
            box = VBox(cfg, require_machine=True)
            last_state = box.state()
            if last_state != "Running":
                last_error = f"VM state is {last_state}"
            else:
                try:
                    last_level = box.guest_additions_run_level()
                except Exception:
                    last_level = None
                with GuestControl(
                    box, credentials["user"], credentials["password"]
                ) as guest:
                    guest.run(
                        r"C:\Windows\System32\cmd.exe",
                        ("/c", "exit", "0"),
                        timeout_ms=30000,
                    )
                write_progress(guest_control=True)
                return {
                    "status": "PASS",
                    "guest_additions_run_level": last_level,
                    "guest_control": True,
                }
        except Exception as exc:
            last_error = repr(exc)
        finally:
            if box is not None:
                box.logoff()
        heartbeat = write_progress(guest_control=False)
        vdi = heartbeat.get("vdi") or {}
        if (
            stall_timeout_seconds is not None
            and last_state == "Running"
            and last_level not in ("Userland", "Desktop")
            and vdi.get("seconds_since_change", 0)
            >= stall_timeout_seconds
        ):
            # No disk writes alone are not enough to declare a stalled Setup:
            # OOBE/update/network waits can legitimately be read-mostly.  Only
            # recover automatically when the framebuffer is also an unchanged,
            # effectively black screen -- the exact failure mode observed on
            # the VirtualBox NEM reboot handoff.
            first_box = VBox(cfg, require_machine=True)
            try:
                first = first_box.framebuffer_evidence()
            finally:
                first_box.logoff()
            time.sleep(3)
            second_box = VBox(cfg, require_machine=True)
            try:
                second = second_box.framebuffer_evidence()
            finally:
                second_box.logoff()

            framebuffer = {
                "first": first,
                "second": second,
                "unchanged": (
                    first.get("sha256") is not None
                    and first.get("sha256") == second.get("sha256")
                ),
            }
            heartbeat["framebuffer"] = framebuffer
            if progress_path is not None:
                Path(progress_path).write_text(
                    json.dumps(heartbeat, indent=2, sort_keys=True) + "\n"
                )
            if (
                first.get("is_black") is True
                and second.get("is_black") is True
                and framebuffer["unchanged"]
            ):
                raise GuestInstallStall(heartbeat)
        time.sleep(5)

    raise TimeoutError(
        "Guest Control did not become ready; "
        f"run_level={last_level!r} last_error={last_error}"
    )
