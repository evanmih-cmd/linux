import unittest
from pathlib import Path

from machine import unc


class MachineTests(unittest.TestCase):
    def test_runner_path_maps_to_windows_unc(self):
        result = unc("/home/github-runner/example/test.iso")
        self.assertEqual(
            result,
            r"\\wsl.localhost\runner02\home\github-runner\example\test.iso",
        )

    def test_non_runner_path_is_rejected(self):
        with self.assertRaises(ValueError):
            unc("/tmp/not-visible-to-vbox.iso")


if __name__ == "__main__":
    unittest.main()
