import json
import shutil
import time
import traceback
from pathlib import Path

from capture import screenshot
from config import Config
from keyboard import Keyboard
from invariants import validate_runtime_serial, validate_source_tree
from machine import reset_vm, unc
from media import build_oemdrv, sha256
from rawserial import RawSerialMonitor
from vbox import VBox

BOOT_SUFFIX = " console=ttyS0,115200 console=tty0 textmode=1"


def alloc_bytes(path):
    return path.stat().st_blocks * 512


class BenchRun:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config()
        self.cfg.runs.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.dir = self.cfg.runs / stamp
        suffix = 0
        while self.dir.exists():
            suffix += 1
            self.dir = self.cfg.runs / f"{stamp}-{suffix}"
        self.dir.mkdir()
        self.events = open(self.dir / "events.jsonl", "a", buffering=1)
        self.stage = "init"
        self.box = None
        self.launch_session = None
        self.term = None
        self.pre = {}
        self.last_event = None
        self.credentials = json.loads(self.cfg.credentials.read_text())
        self.event("run-created", run=str(self.dir))

    def event(self, name, **data):
        row = {"ts": time.time(), "stage": self.stage, "event": name, **data}
        self.last_event = row
        self.events.write(json.dumps(row, sort_keys=True) + "\n")
        print("EVENT", name, json.dumps(data, sort_keys=True), flush=True)

    def set_stage(self, stage):
        self.stage = stage
        self.event("stage", stage_name=stage)
        self.shot(f"stage-{stage}")

    def shot(self, name):
        try:
            helper = VBox(self.cfg)
            try:
                if helper.state() == "Running":
                    screenshot(helper, self.dir / f"{name}.png")
            finally:
                helper.logoff()
        except Exception as exc:
            self.event("screenshot-error", error=repr(exc))

    def snapshot_nvram(self, name):
        helper = VBox(self.cfg)
        try:
            data = helper.nvram_boot_variables()
        finally:
            helper.logoff()
        (self.dir / name).write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        return data

    def cleanup_runs(self):
        dirs = [p for p in self.cfg.runs.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        keep = set(dirs[: self.cfg.keep_runs])
        for status in ("PASS", "FAIL"):
            for run in dirs:
                result = run / "result.json"
                if not result.exists():
                    continue
                try:
                    data = json.loads(result.read_text())
                except Exception:
                    continue
                if data.get("status") == status:
                    keep.add(run)
                    break
        for stale in dirs:
            if stale not in keep and stale != self.dir:
                shutil.rmtree(stale, ignore_errors=True)

    def prepare(self):
        self.set_stage("prepare")
        self.cleanup_runs()

        harness_root = Path(__file__).resolve().parent
        self.event("invariant-check", check="serial-source-policy")
        validate_source_tree(harness_root)

        expected_serial = unc(self.cfg.bench / "serial.log")
        control = VBox(self.cfg)
        try:
            self.event("invariant-check", check="rawfile-com1-pre-run")
            validate_runtime_serial(
                control.serial_config(),
                expected_serial,
                "pre-run",
            )
            state = control.state()
            if state == "Running":
                self.event("teardown-stale-vm", state=state)
                control.poweroff()
                state = control.state()
            if state not in ("PoweredOff", "Saved", "AbortedSaved"):
                raise RuntimeError(f"cannot prepare from VM state {state}")
        finally:
            control.logoff()

        free = shutil.disk_usage(self.cfg.cache).free
        if free < 30 * 1024**3:
            raise RuntimeError(f"low free space: {free}")

        built = build_oemdrv(self.cfg)
        reset = reset_vm(built["iso"], self.cfg)

        post_reset = VBox(self.cfg)
        try:
            self.event("invariant-check", check="rawfile-com1-post-reset")
            validate_runtime_serial(
                post_reset.serial_config(),
                expected_serial,
                "post-reset",
            )
        finally:
            post_reset.logoff()
        target = Path(reset["target"])
        guard = self.cfg.guard
        if not guard.exists():
            raise RuntimeError(f"missing guard disk: {guard}")
        self.pre = {
            "build_id": built["id"],
            "profile_sha256": built["profile_sha"],
            "patch_sha256": built["patch_sha"],
            "oem_sha256": sha256(built["iso"]),
            "official_iso_sha256": sha256(self.cfg.official_iso),
            "target_sha256": sha256(target),
            "target_allocated": alloc_bytes(target),
            "guard_sha256": sha256(guard),
            "free_bytes": free,
        }
        (self.dir / "preflight.json").write_text(
            json.dumps(self.pre, indent=2, sort_keys=True) + "\n"
        )
        self.snapshot_nvram("nvram.before.json")
        self.event("prepared", **self.pre)

    def configure_and_launch(self):
        self.set_stage("launch")
        self.box = VBox(self.cfg)
        if self.box.state() != "PoweredOff":
            raise RuntimeError(f"VM not powered off: {self.box.state()}")
        attachments = self.box.attachments()
        (self.dir / "attachments.json").write_text(
            json.dumps(attachments, indent=2, sort_keys=True) + "\n"
        )
        sata = {
            a["port"]: a["location"]
            for a in attachments
            if a["controller"] == "SATA"
        }
        expected = {
            0: "asus-internal-guard.vdi",
            1: "target.vdi",
            2: "Snapshot20260930-Media.iso",
            3: "oemdrv-",
        }
        for port, needle in expected.items():
            if needle not in sata.get(port, ""):
                raise RuntimeError(f"SATA{port} mismatch: {sata.get(port)}")

        serial_path = self.cfg.bench / "serial.log"
        self.term = RawSerialMonitor(serial_path, self.dir, self.event)
        self.launch_session = self.box.launch()
        self.event(
            "vm-running",
            vm=self.box.actual_vm_name,
            serial=str(serial_path),
        )

    def boot_installer(self):
        self.set_stage("grub")
        self.term.wait_any("Please press", timeout=120)
        keyboard = Keyboard(self.box)
        keyboard.text("t")
        time.sleep(0.7)
        keyboard.edit()
        time.sleep(0.7)
        keyboard.down(4)
        keyboard.end()
        keyboard.text(BOOT_SUFFIX)
        keyboard.ctrl_x()

        self.set_stage("installer-boot")
        self.term.wait_any(
            ["Loading Installation System", "Hardware detection"],
            timeout=240,
        )
        self.term.wait_any(
            "VMBENCH_RECOVERY_READY",
            timeout=480,
        )
        self.event("installer-ready", marker="VMBENCH_RECOVERY_READY")

    def submit_password(self, marker, label, value, next_markers, timeout):
        self.term.wait_any(marker, timeout=240)
        mark = self.term.mark()
        helper = VBox(self.cfg)
        try:
            keyboard = Keyboard(helper)
            keyboard.tab()
            keyboard.text(value)
            keyboard.tab()
            keyboard.text(value)
            keyboard.f10()
            try:
                screenshot(
                    helper,
                    self.dir / (
                        "credential-"
                        + label
                        + "-submitted.png"
                    ),
                )
            except Exception as exc:
                self.event("credential-screenshot-error", error=repr(exc))
        finally:
            helper.logoff()
        return self.term.wait_any(
            next_markers, timeout=timeout, new_since=mark
        )

    def answer_credentials(self):
        self.set_stage("credentials")
        got = self.submit_password(
            "VMBENCH_RECOVERY_READY",
            "recovery",
            self.credentials["recovery"],
            [
                "VMBENCH_TPM_READY",
                "the passwords do not match",
                "Error",
            ],
            timeout=120,
        )
        if got != "VMBENCH_TPM_READY":
            raise RuntimeError(f"recovery credential failed: {got}")

        got = self.submit_password(
            "VMBENCH_TPM_READY",
            "pin",
            self.credentials["pin"],
            [
                "VMBENCH_ROOT_READY",
                "User script store-tpm2-pin failed",
                "the passwords do not match",
                "Error",
            ],
            timeout=120,
        )
        if got != "VMBENCH_ROOT_READY":
            raise RuntimeError(f"TPM PIN credential failed: {got}")

        got = self.submit_password(
            "VMBENCH_ROOT_READY",
            "root",
            self.credentials["root"],
            [
                "VMBENCH_STORAGE_READY",
                "Installation has been aborted",
                "No proposal",
                "Error",
            ],
            timeout=240,
        )
        if got != "VMBENCH_STORAGE_READY":
            raise RuntimeError(f"root/storage transition failed: {got}")
        self.event("credentials-accepted", next_marker=got)

    def wait_for_storage(self):
        self.set_stage("storage")
        target = self.cfg.bench / "target.vdi"
        baseline = alloc_bytes(target)
        deadline = time.time() + 300
        while time.time() < deadline:
            if self.box.state() != "Running":
                break
            time.sleep(0.25)
            current = alloc_bytes(target)
            if current > baseline + 1024 * 1024:
                self.event(
                    "storage-write-started",
                    before=baseline,
                    current=current,
                )
                return
            tail = self.term.tail(40000)
            if "Installation has been aborted" in tail or "No proposal" in tail:
                raise RuntimeError("storage proposal failed")
        raise TimeoutError("storage write did not start")

    def wait_install(self):
        self.set_stage("installing")
        target = self.cfg.bench / "target.vdi"
        last_alloc = alloc_bytes(target)
        last_progress = time.time()
        last_shot = 0.0
        deadline = time.time() + 1800
        while time.time() < deadline:
            state = self.box.state()
            if state != "Running":
                self.event(
                    "vm-stopped",
                    state=state,
                    target_allocated=alloc_bytes(target),
                )
                return
            time.sleep(0.25)
            now = time.time()
            current = alloc_bytes(target)
            if current >= last_alloc + 256 * 1024**2:
                last_alloc = current
                last_progress = now
                self.event("target-progress", allocated=current)
            if now - last_shot > 30:
                self.shot("latest")
                last_shot = now
            tail = self.term.tail(60000)
            if "Installation has been aborted" in tail:
                raise RuntimeError("installer aborted")
            if (
                current > 1024**3
                and any(
                    marker in tail
                    for marker in (
                        "System halted",
                        "Power down",
                        "Installation has finished",
                    )
                )
            ):
                self.event("installer-finished-marker", allocated=current)
                return
            if current > 1024**3 and now - last_progress > 300:
                raise TimeoutError("install stalled after storage progress")
        raise TimeoutError("install timeout")

    def capture_failure_logs(self):
        if not self.box or self.box.state() != "Running":
            return
        try:
            helper = VBox(self.cfg)
            try:
                kb = Keyboard(helper)
                kb.alt_fn(2)
                commands = (
                    "cat /var/log/YaST2/y2log >/dev/ttyS0",
                    "journalctl -b --no-pager >/dev/ttyS0",
                )
                for command in commands:
                    kb.text(command)
                    kb.enter()
                    time.sleep(2)
                kb.alt_fn(7)
            finally:
                helper.logoff()
            time.sleep(8)
            self.term.snapshot("serial-failure.log")
        except Exception as exc:
            self.event("failure-log-capture-error", error=repr(exc))

    def postcheck(self):
        self.set_stage("postcheck")
        target = self.cfg.bench / "target.vdi"
        post = {
            "vm_state": self.box.state() if self.box else None,
            "target_sha256": sha256(target),
            "target_allocated": alloc_bytes(target),
            "guard_sha256": sha256(self.cfg.guard),
        }
        if not self.pre:
            post["guard_unchanged"] = None
            post["target_changed"] = None
            post["nvram_after"] = self.snapshot_nvram("nvram.after.json")
            (self.dir / "postcheck.json").write_text(
                json.dumps(post, indent=2, sort_keys=True) + "\n"
            )
            return post

        post["guard_unchanged"] = (
            post["guard_sha256"] == self.pre["guard_sha256"]
        )
        post["target_changed"] = (
            post["target_sha256"] != self.pre["target_sha256"]
        )
        post["nvram_after"] = self.snapshot_nvram("nvram.after.json")
        (self.dir / "postcheck.json").write_text(
            json.dumps(post, indent=2, sort_keys=True) + "\n"
        )
        if not post["guard_unchanged"]:
            raise RuntimeError("guard disk changed")
        if not post["target_changed"] or post["target_allocated"] < 1024**3:
            raise RuntimeError("target does not contain substantial install")
        self.event("postcheck-pass", **{k: v for k, v in post.items() if k != "nvram_after"})
        return post

    def failure_summary(self, exc, stage):
        reason = str(exc) or exc.__class__.__name__
        why = {
            "prepare": "Harness preparation/safety preflight failed before boot.",
            "launch": "VirtualBox topology or VM launch did not match the required test stand.",
            "grub": "Harness could not drive the selected installer entry through GRUB.",
            "installer-boot": "Installer did not reach the expected VM-proof readiness marker.",
            "credentials": "An AutoYaST credential dialog did not advance to the next expected marker after input.",
            "storage": "All credentials were accepted, but the target VDI did not begin substantial allocation growth; storage planning/commit did not start.",
            "installing": "Destructive storage had started, but installation did not finish or stopped making progress.",
            "postcheck": "Installation reached postcheck, but an invariant such as guard-disk safety or substantial target content failed.",
        }.get(stage, "Harness failed during the recorded stage.")
        return {
            "exception_type": exc.__class__.__name__,
            "reason": reason,
            "why": why,
            "last_event": self.last_event,
        }

    def result(self, status, error=None, post=None, failure=None, stage=None):
        data = {
            "status": status,
            "stage": stage or self.stage,
            "error": error,
            "failure": failure,
            "run": str(self.dir),
            "postcheck": post,
            "evidence": {
                "events": str(self.dir / "events.jsonl"),
                "traceback": str(self.dir / "traceback.txt"),
                "serial_tail": str(self.dir / "serial-tail.txt"),
                "failure_screen": str(self.dir / "failure.png"),
                "serial_failure": str(self.dir / "serial-failure.log"),
                "preflight": str(self.dir / "preflight.json"),
                "postcheck": str(self.dir / "postcheck.json"),
            },
        }
        (self.dir / "result.json").write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        latest = self.cfg.runs / "latest.json"
        latest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        return data

    def close(self):
        if self.term:
            try:
                self.term.close()
            except Exception:
                pass
        if self.box:
            try:
                if self.launch_session:
                    self.box.unlock(self.launch_session)
            except Exception:
                pass
            self.box.logoff()
        self.events.close()


def run(cfg=None):
    bench = BenchRun(cfg)
    try:
        bench.prepare()
        bench.configure_and_launch()
        bench.boot_installer()
        bench.answer_credentials()
        bench.wait_for_storage()
        bench.wait_install()
        post = bench.postcheck()
        bench.stage = "complete"
        bench.event("RUN_PASS")
        return bench.result("PASS", post=post)
    except Exception as exc:
        failure_stage = bench.stage
        failure = bench.failure_summary(exc, failure_stage)
        bench.event(
            "RUN_FAIL",
            failure_stage=failure_stage,
            exception_type=failure["exception_type"],
            reason=failure["reason"],
            why=failure["why"],
        )
        bench.shot("failure")
        bench.capture_failure_logs()
        if bench.term:
            (bench.dir / "serial-tail.txt").write_text(bench.term.tail(120000))
        (bench.dir / "traceback.txt").write_text(traceback.format_exc())
        try:
            post = bench.postcheck()
        except Exception as post_exc:
            post = {
                "postcheck_error": repr(post_exc),
                "vm_state": bench.box.state() if bench.box else None,
            }
        bench.stage = failure_stage
        result = bench.result(
            "FAIL",
            error=repr(exc),
            post=post,
            failure=failure,
            stage=failure_stage,
        )
        print(
            "FAILURE_SUMMARY",
            json.dumps(
                {
                    "stage": failure_stage,
                    "reason": failure["reason"],
                    "why": failure["why"],
                    "result": str(bench.dir / "result.json"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if bench.box and bench.box.state() == "Running":
            try:
                bench.box.poweroff()
                bench.event("powered-off-after-evidence")
            except Exception as power_exc:
                bench.event("poweroff-error", error=repr(power_exc))
        return result
    finally:
        bench.close()
