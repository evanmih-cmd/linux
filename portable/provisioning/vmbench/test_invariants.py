import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

from config import Config
from invariants import (
    BenchInvariantError,
    profile_except_software_sha256,
    validate_proven_profile_except_software,
)


YAST_NS = "http://www.suse.com/1.0/yast2ns"


class ProvenProfileInvariantTests(unittest.TestCase):
    def setUp(self):
        self.profile = Config().profile

    def _mutated_profile(self, mutate):
        tree = ET.parse(self.profile)
        root = tree.getroot()
        mutate(root)
        td = TemporaryDirectory()
        self.addCleanup(td.cleanup)
        path = Path(td.name) / "autoinst.xml"
        tree.write(path, encoding="UTF-8", xml_declaration=True)
        return path

    def test_current_proven_profile_passes(self):
        validate_proven_profile_except_software(self.profile)

    def test_software_section_is_mutable(self):
        def mutate(root):
            software = root.find(f"{{{YAST_NS}}}software")
            packages = software.find(f"{{{YAST_NS}}}packages")
            ET.SubElement(packages, f"{{{YAST_NS}}}package").text = "MozillaFirefox"

        changed = self._mutated_profile(mutate)
        self.assertNotEqual(changed.read_bytes(), self.profile.read_bytes())
        self.assertEqual(
            profile_except_software_sha256(changed),
            profile_except_software_sha256(self.profile),
        )
        validate_proven_profile_except_software(changed)

    def test_software_add_on_section_is_mutable(self):
        def mutate(root):
            add_on = ET.SubElement(root, f"{{{YAST_NS}}}add-on")
            others = ET.SubElement(add_on, f"{{{YAST_NS}}}add_on_others")
            entry = ET.SubElement(others, f"{{{YAST_NS}}}listentry")
            ET.SubElement(entry, f"{{{YAST_NS}}}media_url").text = "cd:///google"

        validate_proven_profile_except_software(self._mutated_profile(mutate))

    def test_known_software_managed_file_is_mutable(self):
        def mutate(root):
            files = ET.SubElement(root, f"{{{YAST_NS}}}files")
            entry = ET.SubElement(files, f"{{{YAST_NS}}}file")
            ET.SubElement(entry, f"{{{YAST_NS}}}file_path").text = (
                "/etc/xdg/mimeapps.list"
            )
            ET.SubElement(entry, f"{{{YAST_NS}}}file_contents").text = "changed"

        validate_proven_profile_except_software(self._mutated_profile(mutate))

    def test_unrelated_file_change_hard_fails(self):
        def mutate(root):
            files = ET.SubElement(root, f"{{{YAST_NS}}}files")
            entry = ET.SubElement(files, f"{{{YAST_NS}}}file")
            ET.SubElement(entry, f"{{{YAST_NS}}}file_path").text = "/etc/shadow"
            ET.SubElement(entry, f"{{{YAST_NS}}}file_contents").text = "changed"

        with self.assertRaises(BenchInvariantError):
            validate_proven_profile_except_software(self._mutated_profile(mutate))

    def test_hostname_change_hard_fails(self):
        def mutate(root):
            hostname = root.find(
                f"{{{YAST_NS}}}networking/"
                f"{{{YAST_NS}}}dns/"
                f"{{{YAST_NS}}}hostname"
            )
            hostname.text = "changed"

        with self.assertRaises(BenchInvariantError):
            validate_proven_profile_except_software(self._mutated_profile(mutate))

    def test_storage_change_hard_fails(self):
        def mutate(root):
            size = root.find(
                f"{{{YAST_NS}}}partitioning/"
                f"{{{YAST_NS}}}drive/"
                f"{{{YAST_NS}}}partitions/"
                f"{{{YAST_NS}}}partition/"
                f"{{{YAST_NS}}}size"
            )
            size.text = "2GiB"

        with self.assertRaises(BenchInvariantError):
            validate_proven_profile_except_software(self._mutated_profile(mutate))

    def test_bootloader_change_hard_fails(self):
        def mutate(root):
            timeout = root.find(
                f"{{{YAST_NS}}}bootloader/"
                f"{{{YAST_NS}}}global/"
                f"{{{YAST_NS}}}timeout"
            )
            timeout.text = "10"

        with self.assertRaises(BenchInvariantError):
            validate_proven_profile_except_software(self._mutated_profile(mutate))

    def test_credential_prompt_change_hard_fails(self):
        def mutate(root):
            question = root.find(
                f"{{{YAST_NS}}}general/"
                f"{{{YAST_NS}}}ask-list/"
                f"{{{YAST_NS}}}ask/"
                f"{{{YAST_NS}}}question"
            )
            question.text = "changed prompt"

        with self.assertRaises(BenchInvariantError):
            validate_proven_profile_except_software(self._mutated_profile(mutate))


if __name__ == "__main__":
    unittest.main()
