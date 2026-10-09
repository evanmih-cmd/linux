import unittest
from pathlib import Path

from config import Config


class HarnessPolicyTests(unittest.TestCase):
    def test_no_vboxmanage_or_legacy_keyboard_transport(self):
        root = Path(__file__).resolve().parent
        forbidden = (
            "VBoxManage",
            "sendScancode",
            "rawserial",
            "keyboard.py",
        )
        violations = []
        for path in root.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            text = path.read_text()
            for token in forbidden:
                if token in text and path.name != "workflow.py":
                    violations.append((path.name, token))
        self.assertEqual(violations, [])

    def test_soap_keyboard_is_bounded_boot_or_one_line_audit(self):
        root = Path(__file__).resolve().parent
        uses = []
        for path in root.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            count = path.read_text().count("IKeyboard_putScancodes")
            if count:
                uses.append((path.name, count))
        # User-approved addition: one short CMD launcher for the installed OS
        # audit, never bulk keyboard transport of scripts/configuration.
        self.assertEqual(uses, [("vbox.py", 1), ("live_audit.py", 1)])
        launcher = (root / "live_audit.py").read_text()
        self.assertIn('command = f"{drive}:\\\\RUN.CMD"', launcher)
        self.assertIn('for char in command:', launcher)
        self.assertNotIn('keyboard_payload', launcher)
        vbox = (root / "vbox.py").read_text()
        self.assertIn("def accept_optical_boot_prompt", vbox)
        self.assertIn("one-line optical-boot prompt only", vbox)
        self.assertIn("USBKeyboard", vbox)

    def test_rejected_usb_answer_path_leaves_no_vm_usb_controller(self):
        root = Path(__file__).resolve().parent
        vbox = (root / "vbox.py").read_text()
        answer = (root / "answer.py").read_text()
        self.assertNotIn("IMachine_addUSBController", vbox)
        self.assertNotIn('"connectionType", "USB"', answer)
        self.assertNotIn('"answer_media_type": "USBStorage"', answer)

    def test_credentials_are_outside_repo(self):
        cfg = Config()
        self.assertNotIn(cfg.repo.resolve(), cfg.credentials.resolve().parents)

    def test_windows_vm_defaults_are_not_linux_defaults(self):
        cfg = Config()
        self.assertEqual(cfg.vm_graphics_controller, "VBoxSVGA")
        self.assertEqual(cfg.vm_keyboard_hid, "USBKeyboard")
        self.assertGreaterEqual(cfg.vm_vram_mib, 128)
        self.assertFalse(cfg.vm_nested_hwvirt)
        self.assertIn("Windows", cfg.vm_name)

    def test_setup_network_is_disabled_until_post_install(self):
        root = Path(__file__).resolve().parent
        vbox = (root / "vbox.py").read_text()
        runner = (root / "runner.py").read_text()
        self.assertIn(
            '("enabled", "false")',
            vbox,
        )
        self.assertIn(
            "box.set_network_enabled(True)",
            runner,
        )

    def test_setup_stage_is_not_claimed_hdd_resumable_after_dvd_boot(self):
        root = Path(__file__).resolve().parent
        runner = (root / "runner.py").read_text()
        self.assertIn('result["stage"] = "setup-running"', runner)
        self.assertIn(
            "before a proven ",
            runner,
        )
        self.assertIn(
            "bootable-disk boundary",
            runner,
        )

    def test_stall_requires_framebuffer_and_never_auto_power_cycles(self):
        root = Path(__file__).resolve().parent
        guest = (root / "guest.py").read_text()
        runner = (root / "runner.py").read_text()
        vbox = (root / "vbox.py").read_text()
        self.assertIn("def framebuffer_evidence", vbox)
        self.assertIn("framebuffer_evidence()", guest)
        self.assertIn("stall-detected.json", runner)
        self.assertNotIn("stalled_box.poweroff()", runner)

    def test_guest_process_lifecycle_uses_iprocess_interface(self):
        guest = (Path(__file__).resolve().parent / "guest.py").read_text()
        self.assertIn('"IProcess_getStatus"', guest)
        self.assertIn('"IProcess_getExitCode"', guest)
        self.assertNotIn('"IGuestProcess_waitForArray"', guest)
        self.assertNotIn('"IGuestProcess_getExitCode"', guest)

    def test_postinstall_single_manifest_dependencies_are_acyclic_and_native(self):
        import yaml
        config = yaml.safe_load(Config().workstation_configuration.read_text())
        resources = config["resources"]
        named = {r["name"]: r for r in resources}
        self.assertEqual(len(named), len(resources))
        for name, resource in named.items():
            for dependency in resource.get("dependsOn", []):
                self.assertIn(dependency, named, f"invalid dependency in {name}")
        self.assertEqual(named["WindowsSandboxFeature"]["type"],
                         "Microsoft.Windows/OptionalFeatureList")
        self.assertEqual(named["EnableVBS"]["dependsOn"], ["DeviceGuardKey"])
        self.assertEqual(named["RequireSecureBootForVBS"]["dependsOn"],
                         ["DeviceGuardKey"])
        self.assertEqual(named["EnableHVCI"]["dependsOn"], ["HVCIScenarioKey"])
        self.assertEqual(
            named["WindowsSandboxFeature"]["properties"]["features"][0]["state"],
            "Installed")

    def test_winget_configuration_opt_in_and_signed_exit_are_handled(self):
        script = (Config().payload / "apply-configuration.ps1").read_text()
        self.assertIn("'configure','--enable'", script)
        self.assertIn("if ($code -eq -1978335127)", script)
        self.assertIn("Invoke-WinGetConfiguration 'retry-apply'", script)
        self.assertIn("CONFIGURATION=FAIL:", script)
        self.assertNotIn("[uint32]$proc.ExitCode", script)
        self.assertIn("3f8b27f648661903d066cc19d5a6e7a8c13bd07eb738d4d765ce7239619b8b5f", script)
        self.assertIn("'--processor-path',$ProcessorPath", script)
        self.assertIn("'settings','--enable','ConfigurationProcessorPath'", script)
        self.assertIn("'settings','--disable','ConfigurationProcessorPath'", script)
        self.assertIn("CONFIGURATION=FAIL_SECURITY_RESTORE", script)
        self.assertIn("finally {", script)
        self.assertEqual(script.count("'settings','--enable','ConfigurationProcessorPath'"), 1)
        self.assertNotIn("processor-path-gate", script)
        self.assertIn("-NoNewWindow", script)
        self.assertIn("'configure','show','-f',$ConfigurationPath,'--processor-path',$ProcessorPath,'--nowarn'", script)
        self.assertNotIn("-WindowStyle Hidden", script)

    def test_post_install_uses_canonical_declarative_configuration(self):
        root = Path(__file__).resolve().parent
        cfg = Config()
        runner = (root / "runner.py").read_text()
        self.assertTrue(cfg.workstation_configuration.is_file())
        self.assertEqual(
            cfg.workstation_configuration,
            cfg.repo / "windows/configuration/workstation.winget",
        )
        self.assertFalse((cfg.payload / "bootstrap.ps1").exists())
        self.assertIn("def configure_guest", runner)
        self.assertIn("cfg.workstation_configuration", runner)
        self.assertIn("cfg.configuration_launcher", runner)
        self.assertIn("interactive vmbench logon is required", runner)
        self.assertNotIn("Invoke-WebRequest", runner)


if __name__ == "__main__":
    unittest.main()
