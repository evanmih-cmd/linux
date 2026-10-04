import json
import shutil
import time
import traceback
from pathlib import Path

from config import Config
from keyboard import Keyboard
from invariants import (
    validate_profile_storage,
    validate_runtime_serial,
    validate_source_tree,
)
from machine import reset_vm, unc
from media import build_oemdrv, load_credentials, sha256
from rawserial import RawSerialMonitor, clean_text
from vbox import VBox

BOOT_SUFFIX = " console=ttyS0,115200 console=tty0 textmode=1"


TPM_PIN_PROMPT = "Please enter TPM2 PIN:"
BOOT_UNLOCK_SUCCESS = "Switching root."
BOOT_UNLOCK_FALLBACK_MARKERS = (
    "falling back to traditional unlocking.",
    "Please enter passphrase for disk ",
)


def classify_boot_unlock(text, *, pin_submitted=False):
    if any(marker in text for marker in BOOT_UNLOCK_FALLBACK_MARKERS):
        return "fallback"
    if BOOT_UNLOCK_SUCCESS in text:
        return "unlocked"
    if pin_submitted and TPM_PIN_PROMPT in text:
        return "pin-reprompt"
    if TPM_PIN_PROMPT in text:
        return "pin-prompt"
    return None



def alloc_bytes(path):
    return path.stat().st_blocks * 512


def persistent_boot_state(data):
    out = {}
    for name, value in data.items():
        if name == "BootOrder":
            out[name] = value
            continue
        if len(name) == 8 and name.startswith("Boot"):
            suffix = name[4:]
            if all(ch in "0123456789abcdefABCDEF" for ch in suffix):
                out[name] = value
    return out


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
        self.nvram_before = None
        self.last_event = None
        self.credential_mode = {
            "embedded": [],
            "missing": ["recovery", "pin", "root"],
        }
        self.boot_pin = None
        self.post_install_boot_mark = None
        self.event("run-created", run=str(self.dir))

    def event(self, name, **data):
        row = {"ts": time.time(), "stage": self.stage, "event": name, **data}
        self.last_event = row
        self.events.write(json.dumps(row, sort_keys=True) + "\n")
        print("EVENT", name, json.dumps(data, sort_keys=True), flush=True)

    def set_stage(self, stage):
        self.stage = stage
        self.event("stage", stage_name=stage)

    def vm_state(self):
        if self.box:
            try:
                return self.box.state()
            except Exception as exc:
                self.event("vbox-state-refresh", error=repr(exc))
        helper = VBox(self.cfg)
        try:
            return helper.state()
        finally:
            helper.logoff()

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

        self.event("invariant-check", check="canonical-storage-profile")
        validate_profile_storage(self.cfg.profile)

        expected_serial_path = self.dir / "serial.log"
        expected_serial = unc(expected_serial_path)
        control = VBox(self.cfg)
        try:
            self.event("invariant-check", check="rawfile-com1-pre-run")
            validate_runtime_serial(
                control.serial_config(),
                None,
                "pre-run",
            )
            state = control.state()
            if state in ("Running", "Paused"):
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
        self.credential_mode = built["credentials"]
        credentials = load_credentials(self.cfg)
        required = {"recovery", "pin", "root"}
        if set(credentials) != required:
            raise RuntimeError(
                "final autonomous E2E requires all three VM test credentials "
                "in the local credential file"
            )
        self.boot_pin = credentials["pin"]
        if not self.boot_pin:
            raise RuntimeError("VM test TPM PIN is empty")
        if credentials["pin"] == credentials["recovery"]:
            raise RuntimeError(
                "VM test TPM PIN must differ from the recovery secret"
            )
        self.event(
            "credential-source",
            embedded=self.credential_mode["embedded"],
            missing=self.credential_mode["missing"],
        )
        reset = reset_vm(
            built["iso"],
            self.cfg,
            serial_path=expected_serial_path,
        )

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
            "credentials_embedded": self.credential_mode["embedded"],
            "credentials_missing": self.credential_mode["missing"],
        }
        (self.dir / "preflight.json").write_text(
            json.dumps(self.pre, indent=2, sort_keys=True) + "\n"
        )
        self.nvram_before = self.snapshot_nvram("nvram.before.json")
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

        serial_path = self.dir / "serial.log"
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
        helper = VBox(self.cfg)
        try:
            keyboard = Keyboard(helper)
            keyboard.text("t")
            time.sleep(0.7)
            keyboard.edit()
            time.sleep(0.7)
            keyboard.down(4)
            keyboard.end()
            keyboard.text(BOOT_SUFFIX)
            keyboard.ctrl_x()
        finally:
            helper.logoff()

        self.set_stage("installer-boot")
        self.term.wait_any(
            ["Loading Installation System", "Hardware detection"],
            timeout=240,
        )
        self.term.wait_any(
            "VMBENCH_PROFILE_READY",
            timeout=480,
        )
        self.event("installer-ready", marker="VMBENCH_PROFILE_READY")

    def answer_credentials(self):
        self.set_stage("credentials")
        missing = list(self.credential_mode["missing"])
        embedded = list(self.credential_mode["embedded"])
        if missing:
            self.event(
                "manual-credential-required",
                missing=missing,
                embedded=embedded,
                why=(
                    "Only credentials absent from the host-side credentials file "
                    "remain as normal AutoYaST prompts. The harness does not type secrets."
                ),
            )
        else:
            self.event(
                "credentials-embedded",
                embedded=embedded,
                why="All installer credentials are carried by the generated OEMDRV.",
            )

    def wait_for_storage(self):
        self.set_stage("storage")
        target = self.cfg.bench / "target.vdi"
        baseline = alloc_bytes(target)
        deadline = time.time() + (1800 if self.credential_mode["missing"] else 300)
        paused_since = None
        while time.time() < deadline:
            state = self.vm_state()
            if state == "Paused":
                if paused_since is None:
                    paused_since = time.time()
                    self.event("vm-transient-paused", phase="storage")
                elif time.time() - paused_since > 30:
                    raise TimeoutError("VM remained paused for more than 30 seconds during storage")
                time.sleep(0.5)
                continue
            paused_since = None
            if state != "Running":
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
        paused_since = None
        deadline = time.time() + 1800
        while time.time() < deadline:
            now = time.time()
            current = alloc_bytes(target)
            tail = self.term.tail(60000)

            if current > 1024**3 and "reboot: Restarting system" in tail:
                self.post_install_boot_mark = self.term.mark()
                self.event(
                    "installer-reboot-observed",
                    allocated=current,
                    serial_mark=self.post_install_boot_mark,
                )
                return

            state = self.vm_state()
            if state == "Paused":
                if paused_since is None:
                    paused_since = now
                    self.event(
                        "vm-transient-paused",
                        phase="installing",
                        target_allocated=current,
                    )
                elif now - paused_since > 30:
                    raise TimeoutError(
                        "VM remained paused for more than 30 seconds during installation"
                    )
                time.sleep(0.5)
                continue
            paused_since = None

            if state != "Running":
                self.event(
                    "vm-stopped",
                    state=state,
                    target_allocated=current,
                )
                raise RuntimeError(
                    "VM stopped before the required normal post-install reboot"
                )

            time.sleep(0.25)
            now = time.time()
            current = alloc_bytes(target)
            if current >= last_alloc + 256 * 1024**2:
                last_alloc = current
                last_progress = now
                self.event("target-progress", allocated=current)
            tail = self.term.tail(60000)
            if "Installation has been aborted" in tail:
                raise RuntimeError("installer aborted")
            if (
                current > 1024**3
                and any(marker in tail for marker in ("System halted", "Power down"))
            ):
                raise RuntimeError(
                    "installer halted instead of performing the required normal reboot"
                )
            if current > 1024**3 and now - last_progress > 300:
                raise TimeoutError("install stalled after storage progress")
        raise TimeoutError("install timeout")

    def verify_tpm_pin_unlock(self):
        self.set_stage("boot-unlock")
        if not self.boot_pin:
            raise RuntimeError("no VM test TPM PIN available for boot unlock")
        if self.post_install_boot_mark is None:
            raise RuntimeError("installer reboot serial mark was not recorded")
        if not self.box or not self.launch_session:
            raise RuntimeError("VirtualBox launch session is unavailable")

        prompt_observed = False
        system_since = None
        deadline = time.time() + 180
        while time.time() < deadline:
            data = self.term._bytes()[self.post_install_boot_mark:]
            clean_boot_text = clean_text(data)
            state = classify_boot_unlock(clean_boot_text, pin_submitted=False)
            if state == "fallback":
                raise RuntimeError(
                    "installed boot fell back to the traditional LUKS passphrase "
                    "before the TPM2 PIN was submitted"
                )
            if state == "unlocked":
                raise RuntimeError(
                    "installed boot reached switch-root without requiring the TPM2 PIN"
                )
            if state == "pin-prompt" and not prompt_observed:
                prompt_observed = True
                self.event("tpm-pin-prompt-observed")

            level = self.box.guest_additions_run_level(self.launch_session)
            if level in ("Userland", "Desktop"):
                raise RuntimeError(
                    "installed system reached userspace before the TPM2 PIN "
                    "was submitted"
                )
            if level == "System":
                if system_since is None:
                    system_since = time.time()
                    self.event(
                        "guest-additions-system-observed",
                        additions_run_level=level,
                    )
                elif time.time() - system_since >= 8:
                    break
            else:
                system_since = None
            time.sleep(0.25)
        else:
            raise TimeoutError(
                "installed kernel did not reach the pre-userspace "
                "Guest Additions system run level"
            )

        helper = VBox(self.cfg)
        try:
            keyboard = Keyboard(helper)
            after_pin = self.term.mark()
            keyboard.text(self.boot_pin)
            keyboard.enter()
        finally:
            helper.logoff()

        self.event(
            "tpm-pin-submitted",
            prompt_observed=prompt_observed,
            pre_pin_additions_run_level="System",
        )

        deadline = time.time() + 120
        while time.time() < deadline:
            text = clean_text(self.term._bytes()[after_pin:])
            state = classify_boot_unlock(text, pin_submitted=True)
            if state == "fallback":
                raise RuntimeError(
                    "TPM2 PIN did not unlock the installed system; "
                    "traditional LUKS fallback was requested"
                )
            if state == "pin-reprompt":
                raise RuntimeError(
                    "TPM2 PIN was rejected and the boot prompt was repeated"
                )

            level = self.box.guest_additions_run_level(self.launch_session)
            if level in ("Userland", "Desktop"):
                self.event(
                    "tpm-pin-unlock-pass",
                    marker=f"Guest Additions {level}",
                    additions_run_level=level,
                    prompt_observed=prompt_observed,
                    fallback_observed=False,
                )
                return
            time.sleep(0.25)

        raise TimeoutError(
            "TPM2 PIN was submitted but installed system never reached "
            "Guest Additions userland"
        )

    def capture_failure_logs(self):
        if self.term:
            try:
                self.term.snapshot("serial-failure.log")
            except Exception as exc:
                self.event("failure-log-capture-error", error=repr(exc))

    def postcheck(self):
        self.set_stage("postcheck")
        target = self.cfg.bench / "target.vdi"
        post = {
            "vm_state": self.vm_state(),
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
        before_boot = persistent_boot_state(self.nvram_before or {})
        after_boot = persistent_boot_state(post["nvram_after"])
        post["persistent_nvram_before"] = before_boot
        post["persistent_nvram_after"] = after_boot
        post["persistent_nvram_unchanged"] = before_boot == after_boot
        (self.dir / "postcheck.json").write_text(
            json.dumps(post, indent=2, sort_keys=True) + "\n"
        )
        if not post["guard_unchanged"]:
            raise RuntimeError("guard disk changed")
        if not post["target_changed"] or post["target_allocated"] < 1024**3:
            raise RuntimeError("target does not contain substantial install")
        if not post["persistent_nvram_unchanged"]:
            raise RuntimeError(
                "persistent UEFI boot state changed: BootOrder/Boot#### must remain unchanged"
            )
        self.event(
            "postcheck-pass",
            **{
                k: v for k, v in post.items()
                if k not in (
                    "nvram_after",
                    "persistent_nvram_before",
                    "persistent_nvram_after",
                )
            },
        )
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
            "boot-unlock": "Installed boot did not prove one-shot TPM2+PIN unlock without traditional LUKS fallback.",
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
            try:
                self.box.logoff()
            except Exception:
                pass
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
        bench.verify_tpm_pin_unlock()
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
        bench.capture_failure_logs()
        if bench.term:
            (bench.dir / "serial-tail.txt").write_text(bench.term.tail(120000))
        (bench.dir / "traceback.txt").write_text(traceback.format_exc())
        try:
            post = bench.postcheck()
        except Exception as post_exc:
            post = {
                "postcheck_error": repr(post_exc),
                "vm_state": bench.vm_state(),
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
        return result
    finally:
        bench.close()

def verify_installed_boot(cfg=None):
    bench = BenchRun(cfg)
    try:
        bench.set_stage("installed-boot-prepare")
        credentials = load_credentials(bench.cfg)
        required = {"recovery", "pin", "root"}
        if set(credentials) != required:
            raise RuntimeError(
                "installed boot verification requires all three VM test credentials"
            )
        if not credentials["pin"]:
            raise RuntimeError("VM test TPM PIN is empty")
        if credentials["pin"] == credentials["recovery"]:
            raise RuntimeError(
                "VM test TPM PIN must differ from the recovery secret"
            )
        bench.boot_pin = credentials["pin"]

        target = bench.cfg.bench / "target.vdi"
        if not target.exists() or alloc_bytes(target) < 1024**3:
            raise RuntimeError("installed target VDI is missing or not substantial")
        if not bench.cfg.guard.exists():
            raise RuntimeError("guard disk is missing")

        control = VBox(bench.cfg)
        try:
            if control.state() != "PoweredOff":
                raise RuntimeError(
                    f"installed boot verification requires PoweredOff VM, got {control.state()}"
                )
            serial_path = bench.dir / "serial.log"
            serial_path.parent.mkdir(parents=True, exist_ok=True)
            if serial_path.exists():
                serial_path.unlink()
            control.set_serial_raw_file(unc(serial_path))
            validate_runtime_serial(
                control.serial_config(),
                unc(serial_path),
                "installed-boot",
            )
            bench.nvram_before = control.nvram_boot_variables()
        finally:
            control.logoff()

        bench.pre = {
            "target_sha256": sha256(target),
            "target_allocated": alloc_bytes(target),
            "guard_sha256": sha256(bench.cfg.guard),
        }
        (bench.dir / "preflight.json").write_text(
            json.dumps(bench.pre, indent=2, sort_keys=True) + "\n"
        )
        (bench.dir / "nvram.before.json").write_text(
            json.dumps(bench.nvram_before, indent=2, sort_keys=True) + "\n"
        )

        bench.set_stage("installed-boot-launch")
        bench.box = VBox(bench.cfg)
        bench.term = RawSerialMonitor(bench.dir / "serial.log", bench.dir, bench.event)
        bench.launch_session = bench.box.launch()
        bench.post_install_boot_mark = 0
        bench.event(
            "installed-boot-vm-running",
            vm=bench.box.actual_vm_name,
            serial=str(bench.dir / "serial.log"),
        )

        deadline = time.time() + 90
        while time.time() < deadline:
            text = clean_text(bench.term._bytes())
            if "openSUSE Tumbleweed 20260930" in text:
                bench.event("installed-systemd-boot-observed")
                break
            if "VMBENCH_PROFILE_READY" in text or "Loading Installation System" in text:
                raise RuntimeError("boot-only probe selected the installer instead of target")
            time.sleep(0.25)
        else:
            raise TimeoutError("installed systemd-boot menu was not observed")

        bench.verify_tpm_pin_unlock()

        bench.set_stage("installed-boot-postcheck")
        after_nvram = bench.snapshot_nvram("nvram.after.json")
        guard_sha = sha256(bench.cfg.guard)
        post = {
            "vm_state": bench.vm_state(),
            "guard_sha256": guard_sha,
            "guard_unchanged": guard_sha == bench.pre["guard_sha256"],
            "target_allocated": alloc_bytes(target),
            "persistent_nvram_unchanged": (
                persistent_boot_state(after_nvram)
                == persistent_boot_state(bench.nvram_before or {})
            ),
        }
        (bench.dir / "postcheck.json").write_text(
            json.dumps(post, indent=2, sort_keys=True) + "\n"
        )
        if not post["guard_unchanged"]:
            raise RuntimeError("guard disk changed during installed boot probe")
        if not post["persistent_nvram_unchanged"]:
            raise RuntimeError("persistent UEFI boot state changed during installed boot probe")

        bench.stage = "complete"
        bench.event("INSTALLED_BOOT_PASS")
        return bench.result("PASS", post=post)
    except Exception as exc:
        failure_stage = bench.stage
        failure = bench.failure_summary(exc, failure_stage)
        bench.event(
            "INSTALLED_BOOT_FAIL",
            failure_stage=failure_stage,
            exception_type=failure["exception_type"],
            reason=failure["reason"],
            why=failure["why"],
        )
        bench.capture_failure_logs()
        if bench.term:
            (bench.dir / "serial-tail.txt").write_text(bench.term.tail(120000))
        (bench.dir / "traceback.txt").write_text(traceback.format_exc())
        result = bench.result(
            "FAIL",
            error=repr(exc),
            failure=failure,
            stage=failure_stage,
        )
        return result
    finally:
        bench.close()
