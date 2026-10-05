import json
import tempfile
import unittest
from pathlib import Path

from software import (
    SoftwareBaselineError,
    _contract_specs,
    _selected_history_packages,
    _verify_opensuse_rpm_signatures,
    load_software_manifest,
)


class FakeConfig:
    def __init__(self, manifest):
        self.software_manifest = Path(manifest)


class SoftwareResolverTests(unittest.TestCase):
    def test_hand_maintained_opensuse_rpm_map_is_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manifest.json"
            path.write_text(json.dumps({
                "schema": 1,
                "opensuse_history": {
                    "base_url": "https://example.invalid/history/",
                    "repomd_sha256": "a" * 64,
                    "rpms": {"x86_64/example.rpm": "b" * 64},
                },
            }))
            with self.assertRaisesRegex(
                SoftwareBaselineError,
                "must be derived from the libzypp transaction",
            ):
                load_software_manifest(FakeConfig(path))

    def test_contract_is_patterns_plus_capability_packages(self):
        manifest = {
            "patterns": ["base", "hardware", "kde_plasma"],
            "packages": ["sddm-qt6", "xorg-x11-server", "MozillaFirefox"],
        }
        self.assertEqual(
            _contract_specs(manifest),
            [
                "pattern:base",
                "pattern:hardware",
                "pattern:kde_plasma",
                "sddm-qt6",
                "xorg-x11-server",
                "MozillaFirefox",
            ],
        )

    def test_empty_opensuse_delta_needs_no_signature_work(self):
        with tempfile.TemporaryDirectory() as td:
            _verify_opensuse_rpm_signatures(Path(td), None, {})

    def test_history_delta_is_selected_from_solver_repository_identity(self):
        xml = """<?xml version='1.0'?>
<stream>
  <install-summary>
    <to-install>
      <solvable type="package" name="from-dvd" edition="1-1" arch="x86_64" repository="dvd"/>
      <solvable type="package" name="delta-a" edition="2-3" arch="x86_64" repository="history"/>
      <solvable type="package" name="delta-b" edition="4-5" arch="noarch" repository="history"/>
      <solvable type="package" name="chrome" edition="6-7" arch="x86_64" repository="google"/>
    </to-install>
  </install-summary>
</stream>
"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "transaction.xml"
            path.write_text(xml)
            self.assertEqual(
                _selected_history_packages(path),
                [
                    ("delta-a", "2-3", "x86_64"),
                    ("delta-b", "4-5", "noarch"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
