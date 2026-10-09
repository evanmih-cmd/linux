import hashlib
import struct
import unittest
import uuid
import zlib
from pathlib import Path

from config import Config
from protected_gpt import SENTINEL, gpt_sectors
from two_disk import dual_config


class ProtectedGPTTests(unittest.TestCase):
    def test_real_gpt_crc_and_layout_and_sentinel(self):
        expected_guid = uuid.UUID("4bf7ca19-1cf7-4821-abab-11df89c64475")
        result = gpt_sectors(8*1024**3, disk_guid=expected_guid)
        blocks = dict(result["writes"])
        primary = blocks[512]
        backup = blocks[8*1024**3-512]
        entries = blocks[1024] + bytes(31*512)
        self.assertEqual(primary[:8], b"EFI PART")
        self.assertEqual(backup[:8], b"EFI PART")
        self.assertEqual(primary[16:20], struct.pack("<I", zlib.crc32(primary[:16]+b"\0"*4+primary[20:92])))
        self.assertEqual(zlib.crc32(entries), struct.unpack_from("<I", primary, 88)[0])
        self.assertEqual(struct.unpack_from("<Q", primary, 24)[0], 1)
        self.assertEqual(struct.unpack_from("<Q", backup, 24)[0], 8*1024**3//512-1)
        self.assertEqual(result["partition_count"], 4)
        self.assertTrue(blocks[result["sentinel_lba"]*512].startswith(SENTINEL))
        self.assertEqual(blocks[0][510:512], b"\x55\xaa")

    def test_separate_cache_and_vm_identity(self):
        prod = Config()
        dual = dual_config(prod)
        self.assertNotEqual(prod.vm_name, dual.vm_name)
        self.assertNotEqual(prod.vm_disk, dual.vm_disk)
        self.assertNotEqual(prod.credentials, dual.credentials)
        self.assertTrue(str(dual.vm_disk).startswith("/home/github-runner/"))
        self.assertEqual(dual.vm_disk_gib, 96)

    def test_refuses_small_protected_disk(self):
        with self.assertRaises(ValueError):
            gpt_sectors(2*1024**3)


if __name__ == "__main__":
    unittest.main()
