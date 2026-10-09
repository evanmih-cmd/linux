import unittest

from unattended import select_windows_11_pro_image


class UnattendedTests(unittest.TestCase):
    def test_selects_exact_pro_not_n(self):
        name, index = select_windows_11_pro_image(
            [
                "Windows 11 Home",
                "Windows 11 Pro",
                "Windows 11 Pro N",
                "Windows 11 Pro Education",
                "Windows 11 Pro for Workstations",
            ],
            ["1", "6", "7", "8", "9"],
        )
        self.assertEqual(name, "Windows 11 Pro")
        self.assertEqual(index, 6)

    def test_ambiguous_or_missing_pro_fails(self):
        with self.assertRaises(RuntimeError):
            select_windows_11_pro_image(
                ["Windows 11 Home", "Windows 11 Pro N"],
                ["1", "2"],
            )

    def test_parallel_arrays_required(self):
        with self.assertRaises(RuntimeError):
            select_windows_11_pro_image(
                ["Windows 11 Pro"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
