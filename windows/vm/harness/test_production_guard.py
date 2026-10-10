"""Release boundary tests: VM access plumbing is allowed in bench only."""
import tempfile
import unittest
from pathlib import Path

from answer import render_autounattend
from config import Config
from production_guard import (
    stage_production_files,
    verify_production_directory,
    verify_production_files,
)

CFG = Config()
BOOTSTRAP = {"user": "owner"}
VM = {"user": CFG.guest_user}


def release_files():
    xml = render_autounattend(
        CFG, BOOTSTRAP,
    )
    return {
        "Autounattend.xml": xml.encode("utf-8"),
        "workstation.winget": CFG.workstation_configuration.read_bytes(),
        "security-hardware.winget": (CFG.repo / "windows/configuration/security-hardware.winget").read_bytes(),
        "sandbox-untrusted.wsb": (CFG.repo / "windows/configuration/sandbox-untrusted.wsb").read_bytes(),
        "sandbox-networked.wsb": (CFG.repo / "windows/configuration/sandbox-networked.wsb").read_bytes(),
    }


class ProductionGuardTests(unittest.TestCase):
    def test_production_contains_no_autologon_or_guest_additions(self):
        files = release_files()
        self.assertEqual(
            verify_production_files(files)["status"],
            "PASS",
        )
        answer = files["Autounattend.xml"].decode()
        for item in ("<AutoLogon>", "FirstLogonCommands", "VBoxWindowsAdditions",
                     "vmbench", "WINBENCH"):
            self.assertNotIn(item, answer)

    def test_vm_uses_the_same_no_extension_xml(self):
        xml = render_autounattend(
            CFG, VM,
        )
        self.assertNotIn("<AutoLogon>", xml)
        self.assertNotIn("VBoxWindowsAdditions", xml)

    def test_refuse_vm_identity_or_implicit_bench_credentials(self):
        files = release_files()
        files["Autounattend.xml"] = render_autounattend(CFG, VM).encode()
        with self.assertRaises(ValueError):
            verify_production_files(files)
        with self.assertRaises(ValueError):
            render_autounattend(CFG, {"user": "owner", "password": "secret"})

    def test_fail_closed_if_autologon_injected_into_release(self):
        files = release_files()
        files["Autounattend.xml"] = files["Autounattend.xml"].replace(
            b"</UserAccounts>",
            b"</UserAccounts><AutoLogon><Enabled>true</Enabled></AutoLogon>",
        )
        with self.assertRaises(ValueError):
            verify_production_files(files)

    def test_release_cannot_masquerade_as_final_owner_account(self):
        files = release_files()
        files["Autounattend.xml"] = files["Autounattend.xml"].replace(
            b"Owner-controlled local account",
            b"Unexpected alternate user",
        )
        with self.assertRaises(ValueError):
            verify_production_files(files)

    def test_fail_closed_for_vm_helpers_on_output(self):
        for name in ("run-configuration-interactive.cmd", "audit.ps1",
                     "vm-only.secret", "payload"):
            with self.subTest(name=name):
                files = release_files()
                files[name] = b"contents"
                with self.assertRaises(ValueError):
                    verify_production_files(files)

    def test_fail_closed_for_vm_markers(self):
        files = release_files()
        files["workstation.winget"] = files["workstation.winget"] + b"\n# VBoxWindowsAdditions\n"
        with self.assertRaises(ValueError):
            verify_production_files(files)
        with self.assertRaises(TypeError):
            verify_production_files(release_files(), target_disk_id=0)

    def test_sandbox_policy_cannot_enable_network_or_clipboard(self):
        for label in (b"<Networking>Enable</Networking>", b"<ClipboardRedirection>Enable</ClipboardRedirection>"):
            files = release_files()
            files["sandbox-untrusted.wsb"] = files["sandbox-untrusted.wsb"].replace(
                b"<Networking>Disable</Networking>" if b"Networking" in label else b"<ClipboardRedirection>Disable</ClipboardRedirection>",
                label,
            )
            with self.assertRaises(ValueError):
                verify_production_files(files)

    def test_sandbox_input_folder_must_be_read_only_and_narrow(self):
        for old, replacement in (
            (b"<ReadOnly>true</ReadOnly>", b"<ReadOnly>false</ReadOnly>"),
            (b"C:\\Sandbox-Inbox", b"C:\\Users"),
            (b"<MappedFolders>", b"<NoMappedFolders>"),
        ):
            files = release_files()
            files["sandbox-untrusted.wsb"] = files["sandbox-untrusted.wsb"].replace(old, replacement)
            with self.assertRaises(ValueError):
                verify_production_files(files)

    def test_common_dsc_never_resets_hardware_uefi_lock(self):
        import yaml
        base = yaml.safe_load(CFG.workstation_configuration.read_text())
        overlay = yaml.safe_load(
            (CFG.repo / "windows/configuration/security-hardware.winget").read_text()
        )
        locked = {
            (entry["keyPath"], entry["valueName"])
            for r in overlay["resources"]
            for entry in r["properties"]["registryEntries"]
        }
        self.assertEqual(len(locked), 2)
        self.assertTrue(all(
            entry["valueData"]["DWord"] == 1 and entry["_exist"] is True
            for r in overlay["resources"]
            for entry in r["properties"]["registryEntries"]
        ))
        for resource in base["resources"]:
            entries = (resource.get("properties") or {}).get("registryEntries") or []
            for entry in entries:
                self.assertNotIn(
                    (entry.get("keyPath"), entry.get("valueName")), locked,
                    "common DSC must not attempt to reverse UEFI Lock"
                )

    def test_refuse_omitted_or_mutated_hardware_uefi_lock(self):
        files = release_files()
        del files["security-hardware.winget"]
        with self.assertRaises(ValueError):
            verify_production_files(files)
        files = release_files()
        files["security-hardware.winget"] = files["security-hardware.winget"].replace(
            b"DWord: 1", b"DWord: 0", 1)
        with self.assertRaises(ValueError):
            verify_production_files(files)

    def test_profiles_have_distinct_explicit_network_capabilities(self):
        import xml.etree.ElementTree as ET
        files = release_files()
        offline = ET.fromstring(files["sandbox-untrusted.wsb"])
        networked = ET.fromstring(files["sandbox-networked.wsb"])
        self.assertEqual(offline.findtext("Networking"), "Disable")
        self.assertEqual(networked.findtext("Networking"), "Enable")
        self.assertEqual(networked.findtext("./LogonCommand/Command"), "resmon.exe")
        for root in (offline, networked):
            self.assertEqual(root.findtext("ProtectedClient"), "Enable")
            self.assertEqual(root.findtext("ClipboardRedirection"), "Disable")
            self.assertEqual(root.findtext("./MappedFolders/MappedFolder/ReadOnly"), "true")
            self.assertEqual(root.findtext("./MappedFolders/MappedFolder/HostFolder"), r"C:\Sandbox-Inbox")
        self.assertEqual(verify_production_files(files)["status"], "PASS")

    def test_networked_profile_forbids_host_write_or_device_redirection(self):
        for before, after in (
            (b"<ReadOnly>true</ReadOnly>", b"<ReadOnly>false</ReadOnly>"),
            (b"<ClipboardRedirection>Disable</ClipboardRedirection>", b"<ClipboardRedirection>Enable</ClipboardRedirection>"),
            (b"<ProtectedClient>Enable</ProtectedClient>", b"<ProtectedClient>Disable</ProtectedClient>"),
            (b"<vGPU>Disable</vGPU>", b"<vGPU>Enable</vGPU>"),
            (b"<LogonCommand>", b"<LogonCommand><Command>powershell.exe</Command>"),
        ):
            with self.subTest(setting=before):
                files = release_files()
                original = files["sandbox-networked.wsb"]
                self.assertIn(before, original)
                files["sandbox-networked.wsb"] = original.replace(before, after)
                with self.assertRaises(ValueError):
                    verify_production_files(files)

    def test_networked_profile_cannot_be_confused_with_offline_profile(self):
        files = release_files()
        files["sandbox-untrusted.wsb"] = files["sandbox-networked.wsb"]
        with self.assertRaises(ValueError):
            verify_production_files(files)

    def test_production_staging_rejects_legacy_fixed_disk_id_before_writing(self):
        # An XML structure check is NOT an install safety proof.
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "production"
            with self.assertRaisesRegex(RuntimeError, "BLOCKED.*RAID"):
                stage_production_files(
                    out, credentials=BOOTSTRAP, cfg=CFG,
                )
            self.assertFalse(out.exists(), "no unsafe answer file may be written")

    def test_legacy_preview_readback_has_explicit_unsafe_status(self):
        files = release_files()
        self.assertFalse(
            verify_production_files(files)["safe_for_asus_install"]
        )
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "preview"
            out.mkdir()
            for name, raw in files.items():
                (out / name).write_bytes(raw)
            preview = verify_production_directory(out, cfg=CFG)
            self.assertEqual(preview["status"], "PASS")
            self.assertEqual(preview["mode"], "UNVERIFIED_MANUAL_SELECTION")
            self.assertFalse(preview["safe_for_asus_install"])
            (out / "elevation-request.ps1").write_text("should fail")
            with self.assertRaises(ValueError):
                verify_production_directory(out, cfg=CFG)


if __name__ == "__main__":
    unittest.main()
