import xml.etree.ElementTree as ET
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from config import Config
from media import render_runtime_profile

YAST_NS = "http://www.suse.com/1.0/yast2ns"


def addon_state(path):
    root = ET.parse(path).getroot()
    add_on = root.find(f"{{{YAST_NS}}}add-on")
    others = add_on.find(f"{{{YAST_NS}}}add_on_others")
    result = []
    for entry in list(others):
        result.append({
            "media_url": entry.find(f"{{{YAST_NS}}}media_url").text,
            "product_dir": entry.find(f"{{{YAST_NS}}}product_dir").text,
        })
    return result


class RuntimeProfileMediaTests(unittest.TestCase):
    def test_vm_runtime_targets_oemdrv_second_medium(self):
        cfg = Config()
        with TemporaryDirectory() as td:
            out = Path(td) / "vm.xml"
            render_runtime_profile(
                cfg,
                out,
                {"recovery": "r", "pin": "p", "root": "x"},
                vm_observability=True,
            )
            self.assertEqual(
                addon_state(out),
                [
                    {
                        "media_url": "cd:/?devices=/dev/sr1",
                        "product_dir": "/portable/google",
                    },
                    {
                        "media_url": "cd:/?devices=/dev/sr1",
                        "product_dir": "/portable/opensuse",
                    },
                ],
            )

    def test_release_runtime_keeps_rufus_repo_relative_layout(self):
        cfg = Config()
        with TemporaryDirectory() as td:
            out = Path(td) / "release.xml"
            render_runtime_profile(
                cfg,
                out,
                {},
                vm_observability=False,
                target_device="/dev/disk/by-id/usb-PORTABLE_TEST",
            )
            self.assertEqual(
                addon_state(out),
                [
                    {
                        "media_url": "repo:/",
                        "product_dir": "/portable/google",
                    },
                    {
                        "media_url": "repo:/",
                        "product_dir": "/portable/opensuse",
                    },
                ],
            )


if __name__ == "__main__":
    unittest.main()
