import unittest
import xml.etree.ElementTree as ET

from answer import render_autounattend
from config import Config
from contract import GERMAN_INPUT, INPUT_LOCALE, SETUP_PRODUCT_KEY, evaluate_autounattend

CREDS = {"user": "owner"}
VM_CREDS = {"user": "owner"}
CFG = Config()


class AnswerFileTests(unittest.TestCase):
    def test_one_renderer_used_for_bench_and_asus(self):
        for credentials, hostname in ((VM_CREDS, "WINBENCH"), (CREDS, "SECUREWS")):
            with self.subTest(hostname=hostname):
                xml = render_autounattend(CFG, credentials, hostname=hostname)
                self.assertEqual(evaluate_autounattend(xml)["status"], "PASS")
                self.assertNotIn("VirtualBox", xml)
                self.assertNotIn("VBoxWindowsAdditions", xml)
                self.assertNotIn("<AutoLogon>", xml)
                self.assertNotIn("FirstLogonCommands", xml)

    def test_canonical_answer_is_identical_to_both_installations(self):
        canonical = (CFG.repo / "windows/vm/deployment/Autounattend.xml").read_text()
        self.assertEqual(render_autounattend(CFG), canonical)
        for name in ("VM", "ASUS"):
            with self.subTest(name=name):
                self.assertEqual(render_autounattend(CFG), canonical)
        self.assertNotIn("<Password>", canonical)
        self.assertNotIn("<AutoLogon>", canonical)
        self.assertNotIn("LogonCount", canonical)

    def test_xml_is_identical_for_identical_inputs(self):
        self.assertEqual(render_autounattend(CFG, CREDS), render_autounattend(CFG, CREDS))
        with self.assertRaises(TypeError):
            render_autounattend(CFG, CREDS, target_disk_id=0)
        with self.assertRaises(TypeError):
            render_autounattend(CFG, CREDS, include_vm_extension=True)

    def test_manual_destination_no_implicit_destructive_op(self):
        xml = render_autounattend(CFG, CREDS)
        root = ET.fromstring(xml)
        namespace = {"u": "urn:schemas-microsoft-com:unattend"}
        setup = next(x for x in root.findall(".//u:component", namespace)
                     if x.get("name") == "Microsoft-Windows-Setup")
        image = setup.find("u:ImageInstall/u:OSImage", namespace)
        self.assertEqual(image.findtext("u:WillShowUI", namespaces=namespace), "Always")
        self.assertIsNone(setup.find("u:DiskConfiguration", namespace))
        self.assertIsNone(image.find("u:InstallTo", namespace))
        self.assertIsNone(image.find("u:InstallToAvailablePartition", namespace))
        for forbidden in ("DiskID", "WillWipeDisk", "CreatePartitions",
                          "ModifyPartitions", "PartitionID"):
            self.assertNotIn(f"<{forbidden}>", xml)

    def test_manual_selection_cannot_be_replaced_by_first_available(self):
        xml = render_autounattend(CFG, CREDS)
        poisoned = xml.replace("</OSImage>", "<InstallToAvailablePartition>true</InstallToAvailablePartition></OSImage>")
        self.assertIn("no-unattended-disk-target-or-layout", evaluate_autounattend(poisoned)["failed"])

    def test_keyboard_exact_and_german_forbidden(self):
        xml = render_autounattend(CFG, CREDS)
        self.assertEqual(xml.count(f"<InputLocale>{INPUT_LOCALE}</InputLocale>"), 2)
        self.assertNotIn(GERMAN_INPUT, xml)
        self.assertNotIn("00000407", xml)

    def test_pro_edition_and_public_key(self):
        xml = render_autounattend(CFG, CREDS)
        self.assertIn("<Value>Windows 11 Pro</Value>", xml)
        self.assertIn(f"<Key>{SETUP_PRODUCT_KEY}</Key>", xml)
        self.assertEqual(xml.count(SETUP_PRODUCT_KEY), 1)

    def test_supported_oobe_only(self):
        xml = render_autounattend(CFG, CREDS)
        for expected in ("<HideOnlineAccountScreens>true</HideOnlineAccountScreens>",
                         "<HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>",
                         "<ProtectYourPC>3</ProtectYourPC>"):
            self.assertIn(expected, xml)
        for forbidden in ("SkipMachineOOBE", "SkipUserOOBE", "BYPASSNRO"):
            self.assertNotIn(forbidden, xml)

    def test_no_password_on_media_and_no_logon_count(self):
        xml = render_autounattend(CFG)
        root = ET.fromstring(xml)
        ns = {"u": "urn:schemas-microsoft-com:unattend"}
        self.assertEqual(
            [x.text for x in root.findall(".//u:LocalAccount/u:Name", ns)],
            ["owner"])
        self.assertEqual(root.findall(".//u:Password", ns), [])
        self.assertEqual(root.findall(".//u:AutoLogon", ns), [])
        self.assertNotIn("LogonCount", xml)
        for credentials in (
            {"user": "owner", "password": "forbidden"},
            {"user": "owner", "password": "test"},
        ):
            with self.assertRaises(ValueError):
                render_autounattend(CFG, credentials)


if __name__ == "__main__":
    unittest.main()
