import unittest

from runner import parse_capability_report


GOOD = '''noise
VMBENCH_CAPABILITY_BEGIN
default_target=graphical.target
display_active=active
display_failed=inactive
desktop_user_account=yes
desktop_home_owner=portable
sddm_process=yes
kwin_wayland_process=yes
plasmashell_process=yes
desktop_session_user=portable
desktop_session_type=wayland
gui_packages=ok
VMBENCH_CAPABILITY_END
'''


class CapabilityReportTests(unittest.TestCase):
    def test_good_graphical_report_passes(self):
        facts = parse_capability_report(GOOD)
        self.assertEqual(facts['desktop_session_user'], 'portable')
        self.assertEqual(facts['desktop_session_type'], 'wayland')

    def test_missing_plasmashell_hard_fails(self):
        bad = GOOD.replace(
            'plasmashell_process=yes', 'plasmashell_process=no'
        )
        with self.assertRaisesRegex(RuntimeError, 'plasmashell_process'):
            parse_capability_report(bad)

    def test_wrong_session_user_hard_fails(self):
        bad = GOOD.replace(
            'desktop_session_user=portable', 'desktop_session_user=root'
        )
        with self.assertRaisesRegex(RuntimeError, 'desktop_session_user'):
            parse_capability_report(bad)

    def test_incomplete_report_hard_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'complete first-boot'):
            parse_capability_report('VMBENCH_CAPABILITY_BEGIN\n')


if __name__ == '__main__':
    unittest.main()
