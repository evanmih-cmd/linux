import fcntl
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from runner import (
    _clear_active_install,
    _load_active_install,
    _persist_active_install,
    _single_install_controller,
    resume_install,
)


@dataclass
class FakeConfig:
    runs: Path


class RunnerStateTests(unittest.TestCase):
    def test_active_install_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FakeConfig(Path(tmp) / "runs")
            run_dir = cfg.runs / "20261007-000000-install"
            run_dir.mkdir(parents=True)
            saved = _persist_active_install(
                cfg, run_dir, "setup-running"
            )
            loaded = _load_active_install(cfg)
            self.assertEqual(loaded["run"], str(run_dir))
            self.assertEqual(loaded["stage"], "setup-running")
            self.assertEqual(saved["stage"], loaded["stage"])
            _clear_active_install(cfg, run_dir)
            self.assertIsNone(_load_active_install(cfg))

    def test_clear_refuses_to_delete_a_different_active_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FakeConfig(Path(tmp) / "runs")
            run_a = cfg.runs / "20261007-000000-install"
            run_b = cfg.runs / "20261007-000001-install"
            run_a.mkdir(parents=True)
            run_b.mkdir(parents=True)
            _persist_active_install(cfg, run_a, "setup-running")
            with self.assertRaises(RuntimeError):
                _clear_active_install(cfg, run_b)
            self.assertEqual(_load_active_install(cfg)["run"], str(run_a))

    def test_resume_without_active_install_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FakeConfig(Path(tmp) / "runs")
            result = resume_install(cfg)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["stage"], "resume")
            self.assertIn("no active install", result["error"])

    def test_early_stage_is_not_resumed_destructively(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FakeConfig(Path(tmp) / "runs")
            run_dir = cfg.runs / "20261007-000000-install"
            run_dir.mkdir(parents=True)
            _persist_active_install(cfg, run_dir, "reset")
            result = resume_install(cfg)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("safely resumable boundary", result["error"])

    def test_second_install_controller_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FakeConfig(Path(tmp) / "runs")
            cfg.runs.mkdir(parents=True)
            lock_path = cfg.runs / "install-controller.lock"
            with lock_path.open("a+") as held:
                fcntl.flock(
                    held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                )

                @_single_install_controller
                def dummy(config):
                    return {"status": "PASS"}

                result = dummy(cfg)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["stage"], "controller-lock")


class MixedInstallSafetyTests(__import__("unittest").TestCase):
    def test_fresh_install_cannot_wipe_canonical_single_disk_vm(self):
        from unittest.mock import patch
        from runner import _fresh_install
        with patch("runner.reset_vm", side_effect=AssertionError("must not reset")):
            result = _fresh_install()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["stage"], "two-disk-install-not-implemented")


if __name__ == "__main__":
    unittest.main()
