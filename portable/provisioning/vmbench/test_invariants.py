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

    def test_software_section_is_the_only_mutable_top_level_section(self):
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
