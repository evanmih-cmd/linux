import fcntl
import functools
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from answer import attach_install_media
from audit import run_audit
from config import Config
from guest import (
    GuestControl,
    GuestInstallStall,
    wait_for_guest_additions,
    wait_for_guest_control,
)
from machine import reset_vm, vm_status
from media import load_or_create_credentials
from vbox import VBox
from workflow import static_check


def _run_dir(cfg, prefix):
    cfg.runs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = cfg.runs / f"{stamp}-{prefix}"
    path.mkdir()
    return path


def _write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _active_install_path(cfg):
    return cfg.runs / "active-install.json"


def _single_install_controller(func):
    @functools.wraps(func)
    def wrapped(cfg=None, *args, **kwargs):
        cfg = cfg or Config()
        cfg.runs.mkdir(parents=True, exist_ok=True)
        lock_path = cfg.runs / "install-controller.lock"
        lock_file = lock_path.open("a+")
        try:
            try:
                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except BlockingIOError:
                return {
                    "status": "FAIL",
                    "stage": "controller-lock",
                    "error": (
                        "another install/resume controller is already active"
                    ),
                }
            return func(cfg, *args, **kwargs)
        finally:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                lock_file.close()

    return wrapped


def _persist_active_install(cfg, run_dir, stage):
    cfg.runs.mkdir(parents=True, exist_ok=True)
    state = {
        "run": str(run_dir),
        "stage": stage,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(_active_install_path(cfg), state)
    return state


def _load_active_install(cfg):
    path = _active_install_path(cfg)
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _clear_active_install(cfg, expected_run):
    active = _load_active_install(cfg)
    if not active:
        return False
    actual_run = Path(active["run"]).resolve()
    expected = Path(expected_run).resolve()
    if actual_run != expected:
        raise RuntimeError(
            "refusing to clear a different active install run: "
            f"expected={expected} actual={actual_run}"
        )
    _active_install_path(cfg).unlink()
    return True


def prune_runs(cfg=None):
    cfg = cfg or Config()
    cfg.runs.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        [p for p in cfg.runs.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    for stale in rows[cfg.keep_runs:]:
        shutil.rmtree(stale)


def wait_vm_state(box, wanted, timeout_seconds=180):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = box.state()
        if last == wanted:
            return last
        time.sleep(2)
    raise TimeoutError(
        f"VM did not reach {wanted}; last state was {last}"
    )


def configure_guest(cfg=None):
    cfg = cfg or Config()
    credentials = load_or_create_credentials(cfg)
    run_dir = _run_dir(cfg, "configure")
    result = {
        "status": "FAIL",
        "run": str(run_dir),
        "configuration": str(cfg.workstation_configuration),
    }

    try:
        box = VBox(cfg, require_machine=True)
        try:
            state = box.state()
            if state == "PoweredOff":
                box.set_network_enabled(True)
            elif state == "Running":
                network = box.network_config()
                if not network["enabled"]:
                    raise RuntimeError(
                        "post-install configuration requires network enabled; "
                        "power off the installed-clean VM before enabling NAT"
                    )
            else:
                raise RuntimeError(
                    "configuration requires PoweredOff/Running VM, "
                    f"got {state}"
                )
        finally:
            box.logoff()

        if state == "PoweredOff":
            start_vm(cfg, accept_optical_boot=False)

        box = VBox(cfg, require_machine=True)
        try:
            wait_for_guest_additions(box, timeout_seconds=600)
            with GuestControl(
                box, credentials["user"], credentials["password"]
            ) as guest:
                # WinGet/AppX and user-scoped Windows settings require a real
                # interactive profile.  A Guest Control secondary logon is not
                # a substitute for the console user session.
                try:
                    guest.run(
                        r"C:\Windows\System32\cmd.exe",
                        (
                            "/d",
                            "/s",
                            "/c",
                            f"quser {credentials['user']} >nul 2>&1",
                        ),
                        timeout_ms=30000,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        "interactive vmbench logon is required before "
                        "post-install WinGet Configuration"
                    ) from exc

                guest.ensure_directory(cfg.guest_work_dir)
                guest_config = guest.copy_to_guest(
                    cfg.workstation_configuration,
                    cfg.guest_work_dir,
                )
                launcher = guest.copy_to_guest(
                    cfg.configuration_launcher,
                    cfg.guest_work_dir,
                )
                command = (
                    f"& '{launcher}' "
                    f"-ConfigurationPath '{guest_config}'"
                )
                try:
                    guest.powershell(command, timeout_ms=1800000)
                finally:
                    try:
                        guest.copy_from_guest(
                            cfg.guest_work_dir + r"\configuration.log",
                            run_dir,
                        )
                    except Exception:
                        pass
        finally:
            box.logoff()

        result.update(
            {
                "status": "PASS",
                "stage": "configured",
                "declarative": True,
            }
        )
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        _write(run_dir / "result.json", result)

    return result


def bootstrap_guest(cfg=None, install_chrome=True):
    # Compatibility alias.  The old imperative bootstrap path is retired;
    # all post-install convergence now goes through the canonical WinGet/DSC
    # desired-state document.
    return configure_guest(cfg)


def shutdown_guest(cfg=None):
    cfg = cfg or Config()
    credentials = load_or_create_credentials(cfg)
    box = VBox(cfg, require_machine=True)
    try:
        if box.state() == "PoweredOff":
            return {"status": "PASS", "already_off": True}
        if box.state() != "Running":
            raise RuntimeError(
                f"graceful shutdown requires Running VM, got {box.state()}"
            )
        with GuestControl(
            box, credentials["user"], credentials["password"]
        ) as guest:
            guest.run(
                r"C:\Windows\System32\shutdown.exe",
                (
                    "/s",
                    "/t",
                    "0",
                    "/d",
                    "p:4:1",
                    "/c",
                    "Desktop Windows harness checkpoint",
                ),
                timeout_ms=30000,
            )
        wait_vm_state(box, "PoweredOff", timeout_seconds=180)
        return {"status": "PASS", "already_off": False}
    finally:
        box.logoff()


def snapshot(name, cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg, require_machine=True)
    try:
        if box.state() != "PoweredOff":
            raise RuntimeError(
                "checkpoint snapshots are taken only from PoweredOff state"
            )
        snapshot_id = box.take_snapshot(
            name, "Desktop Windows VM harness checkpoint"
        )
        return {
            "status": "PASS",
            "name": name,
            "id": snapshot_id,
        }
    finally:
        box.logoff()


def restore(name, cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg, require_machine=True)
    try:
        box.restore_snapshot(name)
        return {"status": "PASS", "name": name}
    finally:
        box.logoff()


def start_vm(cfg=None, accept_optical_boot=False):
    cfg = cfg or Config()
    box = VBox(cfg, require_machine=True)
    try:
        if box.state() == "Running":
            return {"status": "PASS", "already_running": True}
        if box.state() != "PoweredOff":
            raise RuntimeError(f"cannot start VM from {box.state()}")
        session = box.launch()
        # The returned launch session belongs to the running VM.  Release our
        # client reference; the VM process remains running.
        try:
            box.unlock(session)
        except Exception:
            pass
        wait_vm_state(box, "Running", timeout_seconds=60)

        boot_prompt = None
        if accept_optical_boot:
            boot_prompt = box.accept_optical_boot_prompt()

        return {
            "status": "PASS",
            "already_running": False,
            "boot_prompt": boot_prompt,
        }
    finally:
        box.logoff()


def _publish_install_result(cfg, run_dir, result):
    _write(run_dir / "result.json", result)
    cfg.runs.mkdir(parents=True, exist_ok=True)
    _write(cfg.runs / "latest.json", result)


def _continue_install(cfg, run_dir, result, stage):
    if stage in ("setup-running", "await-guest-control"):
        box = VBox(cfg, require_machine=True)
        try:
            state = box.state()
        finally:
            box.logoff()

        if state == "PoweredOff":
            if stage == "setup-running":
                raise RuntimeError(
                    "Setup stopped while the VM is PoweredOff before a proven "
                    "bootable-disk boundary. Refusing to guess or boot the HDD; "
                    "inspect the framebuffer/disk and use an explicit recovery "
                    "or clean reinstall."
                )
            start_vm(cfg, accept_optical_boot=False)
        elif state != "Running":
            raise RuntimeError(
                f"cannot continue install from VM state {state!r}"
            )

        result["stage"] = stage
        _persist_active_install(cfg, run_dir, stage)

        try:
            readiness = wait_for_guest_control(
                cfg,
                timeout_seconds=cfg.install_timeout_minutes * 60,
                progress_path=run_dir / "install-heartbeat.json",
                stall_timeout_seconds=cfg.install_stall_minutes * 60,
            )
        except GuestInstallStall as exc:
            evidence = {
                "status": "DETECTED",
                "heartbeat": exc.heartbeat,
                "action": (
                    "none: controller stopped for explicit framebuffer review; "
                    "no automatic VM power action was taken"
                ),
            }
            _write(run_dir / "stall-detected.json", evidence)
            raise

        _write(run_dir / "guest-control.json", readiness)
        stage = "base-checkpoint"
        result["stage"] = stage
        _persist_active_install(cfg, run_dir, stage)

    if stage == "base-checkpoint":
        base_file = run_dir / "base-snapshot.json"
        if not base_file.is_file():
            box = VBox(cfg, require_machine=True)
            try:
                state = box.state()
            finally:
                box.logoff()
            if state == "Running":
                shutdown_guest(cfg)
            elif state != "PoweredOff":
                raise RuntimeError(
                    f"cannot checkpoint install from VM state {state!r}"
                )
            base_snapshot = snapshot("installed-clean", cfg)
            _write(base_file, base_snapshot)

        result.update(
            {
                "status": "PASS",
                "stage": "installed-clean",
                "snapshot": "installed-clean",
                "guest_control": True,
                "post_install_configuration_applied": False,
            }
        )
        _publish_install_result(cfg, run_dir, result)
        _clear_active_install(cfg, run_dir)
        prune_runs(cfg)
        return result

    raise RuntimeError(f"unsupported resumable install stage {stage!r}")


@_single_install_controller
def resume_install(cfg=None):
    cfg = cfg or Config()
    active = _load_active_install(cfg)
    if not active:
        return {
            "status": "FAIL",
            "stage": "resume",
            "error": "no active install run",
        }

    run_dir = Path(active["run"])
    if not run_dir.is_dir():
        return {
            "status": "FAIL",
            "stage": "resume",
            "error": f"active run directory is missing: {run_dir}",
        }

    stage = active.get("stage")
    if stage not in (
        "setup-running",
        "await-guest-control",
        "base-checkpoint",
    ):
        return {
            "status": "FAIL",
            "stage": "resume",
            "run": str(run_dir),
            "error": (
                "active install stopped before the safely resumable boundary; "
                f"stage={stage!r}. Start a new clean install instead."
            ),
        }

    result_file = run_dir / "result.json"
    if result_file.is_file():
        try:
            result = json.loads(result_file.read_text())
        except Exception:
            result = {}
    else:
        result = {}
    result.update(
        {
            "status": "FAIL",
            "run": str(run_dir),
            "stage": stage,
            "resumed": True,
        }
    )
    result.pop("error", None)

    try:
        return _continue_install(cfg, run_dir, result, stage)
    except Exception as exc:
        result["error"] = repr(exc)
        _publish_install_result(cfg, run_dir, result)
        return result


def _fresh_install(cfg=None):
    cfg = cfg or Config()
    # Installation has changed from single-disk fully unattended to two-disk
    # operator-controlled Setup. The legacy reset/boot flow below is not
    # release-safe: it would destroy the canonical VM and then wait for Guest
    # Control, although the common XML no longer bootstraps Guest Additions.
    # Reject BEFORE creating a run or invoking reset_vm. A later patch must
    # replace the install state machine with a real manual-UI pause, a
    # protected sentinel VDI and separate Guest Additions transport.
    return {
        "status": "FAIL",
        "stage": "two-disk-install-not-implemented",
        "error": (
            "Destructive one-disk reinstall BLOCKED. Common answer XML "
            "requires protected VDI Offline + manual target selection; "
            "two-disk VM flow and Guest Additions bootstrap are not yet "
            "implemented. Existing installed-clean VM remains intact."
        ),
    }
    if _load_active_install(cfg):
        return {
            "status": "FAIL",
            "stage": "preflight",
            "error": (
                "an active install run already exists; use 'resume' or "
                "cancel it before starting another destructive install"
            ),
        }

    run_dir = _run_dir(cfg, "install")
    result = {
        "status": "FAIL",
        "run": str(run_dir),
        "stage": "preflight",
        "resumed": False,
    }
    _persist_active_install(cfg, run_dir, "preflight")

    try:
        preflight = static_check(cfg)
        _write(run_dir / "preflight.json", preflight)
        if preflight["status"] != "PASS":
            raise RuntimeError("static preflight failed")

        result["stage"] = "reset"
        _persist_active_install(cfg, run_dir, "reset")
        created = reset_vm(cfg)
        _write(run_dir / "vm-created.json", created)

        result["stage"] = "answer-media"
        _persist_active_install(cfg, run_dir, "answer-media")
        answer_media = attach_install_media(cfg)
        _write(run_dir / "answer-media.json", answer_media)
        if answer_media.get("answer_media_type") != "DVD":
            raise RuntimeError(
                "VM Joliet test requires read-only DVD answer media; "
                f"got {answer_media.get('answer_media_type')!r}"
            )
        verification = answer_media.get("answer_media_verification") or {}
        if (
            verification.get("status") != "PASS"
            or verification.get("has_joliet") is not True
            or verification.get("joliet_names") != ["Autounattend.xml"]
        ):
            raise RuntimeError(
                "answer Joliet DVD verification failed: "
                f"{verification!r}"
            )

        result["stage"] = "boot"
        _persist_active_install(cfg, run_dir, "boot")
        boot = start_vm(cfg, accept_optical_boot=True)
        _write(run_dir / "boot.json", boot)

        result["stage"] = "setup-running"
        _persist_active_install(cfg, run_dir, "setup-running")
        return _continue_install(
            cfg, run_dir, result, "setup-running"
        )
    except Exception as exc:
        result["error"] = repr(exc)
        _publish_install_result(cfg, run_dir, result)
        # Once boot completed, preserving active state permits a later resume.
        # Earlier stages are deliberately fail-closed and require a new run.
        if result["stage"] not in (
            "setup-running",
            "await-guest-control",
            "base-checkpoint",
        ):
            _clear_active_install(cfg, run_dir)
        prune_runs(cfg)
        return result



@_single_install_controller
def install(cfg=None):
    cfg = cfg or Config()
    box = VBox(cfg)
    try:
        machine_exists = bool(box.machine)
    finally:
        box.logoff()
    if machine_exists or cfg.vm_disk.exists():
        return {
            "status": "FAIL",
            "stage": "destructive-protection",
            "error": (
                "existing VM/VDI present; 'install' is non-destructive. "
                "Use 'resume' to continue it or explicit 'reinstall' "
                "to destroy and recreate it."
            ),
        }
    return _fresh_install(cfg)


@_single_install_controller
def reinstall(cfg=None):
    cfg = cfg or Config()
    return _fresh_install(cfg)


def audit_only(cfg=None):
    cfg = cfg or Config()
    run_dir = _run_dir(cfg, "audit")
    result = run_audit(run_dir, cfg)
    _write(
        run_dir / "result.json",
        {
            "status": result["status"],
            "run": str(run_dir),
            "failed": result["failed"],
            "warnings": result["warnings"],
            "not_provable_in_vm": result["not_provable_in_vm"],
        },
    )
    prune_runs(cfg)
    return result


def status(cfg=None):
    cfg = cfg or Config()
    return vm_status(cfg)
