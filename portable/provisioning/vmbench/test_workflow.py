import unittest

from config import Config
from workflow import _validate_vm_graphics_contract


class VMGraphicsContractTests(unittest.TestCase):
    def test_supported_linux_graphics_passes(self):
        cfg = Config(
            vm_graphics_controller="VMSVGA",
            vm_vram_mib=128,
            vm_accel3d=False,
        )
        self.assertEqual(
            _validate_vm_graphics_contract(cfg),
            {"controller": "VMSVGA", "vram_mib": 128, "accel3d": False},
        )

    def test_legacy_vboxvga_hard_fails(self):
        cfg = Config(vm_graphics_controller="VBoxVGA", vm_vram_mib=128)
        with self.assertRaisesRegex(RuntimeError, "must be VMSVGA"):
            _validate_vm_graphics_contract(cfg)

    def test_tiny_vram_hard_fails(self):
        cfg = Config(vm_graphics_controller="VMSVGA", vm_vram_mib=8)
        with self.assertRaisesRegex(RuntimeError, "at least 64 MiB"):
            _validate_vm_graphics_contract(cfg)


if __name__ == "__main__":
    unittest.main()
