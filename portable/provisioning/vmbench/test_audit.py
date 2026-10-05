import json
import unittest

from audit import (
    AuditFailure,
    audit_launcher,
    build_probe_script,
    evaluate,
    probe_commands,
    summarize,
    validate_probe_commands,
)
from keyboard import Keyboard


def good_sections():
    sections = {
        name: {"rc": 0, "output": ""}
        for name, _ in probe_commands()
    }
    sections["uid"]["output"] = "0"
    sections["hostname"]["output"] = "portable"
    sections["etc_hostname"]["output"] = "portable"
    sections["os_release"]["output"] = (
        'NAME="openSUSE Tumbleweed"\n'
        'ID="opensuse-tumbleweed"\n'
    )
    sections["kernel"]["output"] = "7.2.8-1-default"
    sections["target_device"]["output"] = "/dev/sdb"
    sections["lsblk"]["output"] = json.dumps({
        "blockdevices": [
            {
                "name": "sda",
                "path": "/dev/sda",
                "type": "disk",
                "size": 8 * 1024**3,
                "children": [],
            },
            {
                "name": "sdb",
                "path": "/dev/sdb",
                "type": "disk",
                "size": 48 * 1024**3,
                "children": [
                    {
                        "name": "sdb1",
                        "path": "/dev/sdb1",
                        "type": "part",
                        "size": 1024**3,
                        "fstype": "vfat",
                        "fsver": "FAT32",
                        "parttype": "c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                        "mountpoints": ["/boot/efi"],
                    },
                    {
                        "name": "sdb2",
                        "path": "/dev/sdb2",
                        "type": "part",
                        "size": 47 * 1024**3,
                        "fstype": "crypto_LUKS",
                        "fsver": "2",
                        "mountpoints": [None],
                    },
                ],
            },
        ]
    })
    sections["findmnt"]["output"] = "\n".join([
        'TARGET="/" SOURCE="/dev/mapper/system-root" FSTYPE="btrfs" OPTIONS="rw"',
        'TARGET="/home" SOURCE="/dev/mapper/system-home" FSTYPE="xfs" OPTIONS="rw"',
        'TARGET="/boot/efi" SOURCE="/dev/sdb1" FSTYPE="vfat" OPTIONS="rw"',
    ])
    sections["pvs"]["output"] = json.dumps({
        "report": [{"pv": [{"pv_name": "/dev/mapper/crypt", "vg_name": "system"}]}]
    })
    sections["vgs"]["output"] = json.dumps({
        "report": [{"vg": [{"vg_name": "system", "vg_size": "47g", "vg_free": "1g"}]}]
    })
    sections["lvs"]["output"] = json.dumps({
        "report": [{"lv": [
            {"vg_name": "system", "lv_name": "root", "lv_size": "24g"},
            {"vg_name": "system", "lv_name": "home", "lv_size": "21g"},
            {"vg_name": "system", "lv_name": "swap", "lv_size": "2g"},
        ]}]
    })
    sections["swapon"]["output"] = "/dev/dm-3 2147483648 partition"
    sections["fstab"]["output"] = "\n".join([
        "UUID=r / btrfs defaults 0 0",
        "UUID=h /home xfs defaults 0 0",
        "UUID=e /boot/efi vfat defaults 0 0",
        "/dev/mapper/system-swap swap swap defaults 0 0",
    ])
    sections["crypttab"]["output"] = (
        "crypt UUID=luks none "
        "tpm2-device=auto,x-initrd.attach,tpm2-measure-pcr=yes"
    )
    sections["luks_json"]["output"] = json.dumps({
        "keyslots": {"0": {}, "1": {}},
        "tokens": {
            "0": {
                "type": "systemd-tpm2",
                "tpm2-pin": True,
                "keyslots": ["1"],
            }
        },
    })
    sections["btrfs_subvols"]["output"] = (
        "ID 256 gen 1 top level 5 path @\n"
        "ID 257 gen 1 top level 256 path @/.snapshots"
    )
    sections["btrfs_default"]["output"] = (
        "ID 256 gen 1 top level 5 path @"
    )
    sections["snapper_configs"]["output"] = (
        "Config | Subvolume\nroot | /"
    )
    sections["snapper_root"]["output"] = (
        "#,Type,Pre #,Date,User,Cleanup,Description,Userdata\n"
        "1,single,,now,root,,before installation,\n"
        "2,single,,now,root,,after installation,"
    )
    sections["boot_files"]["output"] = "\n".join([
        "EFI/BOOT/BOOTX64.EFI",
        "EFI/systemd/pcrlock.json",
        "EFI/systemd/measure-pcr-prediction",
        "loader/entries/opensuse.conf",
        "opensuse/vmlinuz",
        "opensuse/initrd",
    ])
    sections["bls"]["output"] = (
        "title openSUSE\n"
        "linux /opensuse/vmlinuz\n"
        "initrd /opensuse/initrd"
    )
    sections["bls_missing"]["output"] = ""
    sections["nm_files"]["output"] = ""
    sections["nm_effective"]["output"] = "[main]\nplugins=keyfile"
    sections["nm_service"]["output"] = "active"
    sections["failed_units"]["output"] = ""
    sections["system_state"]["output"] = "running"
    sections["packages"]["output"] = "\n".join([
        "sdbootutil-1", "snapper-1", "NetworkManager-1", "lvm2-1"
    ])
    sections["software_packages"]["output"] = "\n".join([
        "MozillaFirefox-1",
        "google-chrome-stable-1",
        "NetworkManager-1",
        "plasma6-nm-1",
        "wpa_supplicant-1",
        "firewalld-1",
        "transactional-update-1",
        "zypp-boot-plugin-1",
        "sdbootutil-tukit-1",
    ])
    sections["software_patterns"]["output"] = "\n".join([
        "patterns-base-base-1",
        "patterns-base-hardware-1",
        "patterns-kde-kde_plasma-1",
    ])
    sections["software_forbidden"]["output"] = ""
    sections["package_closure"]["output"] = "\n".join([
        "MozillaFirefox-1.x86_64",
        "google-chrome-stable-1.x86_64",
    ])
    sections["software_files"]["output"] = "\n".join([
        "0a67fa9b7024048f7f967fef8d33c2da38dae9354e996c131b79a014f62b7efc  /etc/udev/rules.d/20-hw1.rules",
        "37ac8c63e1d018a3472eba490d66c69c3a085aa7654035d05707f153c3248df6  /etc/xdg/mimeapps.list",
    ])
    sections["firewalld_state"]["output"] = "enabled=enabled\nactive=active"
    sections["pin_file_absent"]["output"] = ""
    return sections


class AuditTests(unittest.TestCase):
    def test_good_fixture_passes(self):
        result = summarize(evaluate(good_sections()))
        self.assertEqual(result["status"], "PASS", result)

    def test_hostname_drift_fails(self):
        fixture = good_sections()
        fixture["hostname"]["output"] = "install"
        fixture["etc_hostname"]["output"] = "install"
        result = summarize(evaluate(fixture))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("hostname", result["failed"])

    def test_ansi_colored_kdump_only_is_warning(self):
        fixture = good_sections()
        fixture["failed_units"]["output"] = (
            "\x1b[0;1;31mkdump-early.service\x1b[0m loaded failed\n"
            "\x1b[0;1;31mkdump.service\x1b[0m loaded failed\n"
            "\x1b[K"
        )
        fixture["system_state"]["output"] = "degraded"
        result = summarize(evaluate(fixture))
        self.assertEqual(result["status"], "PASS", result)
        self.assertIn("failed-units", result["warnings"])
        self.assertIn("system-state", result["warnings"])

    def test_forbidden_probe_is_successful_when_nothing_is_installed(self):
        command = dict(probe_commands())["software_forbidden"]
        self.assertTrue(command.endswith("; true"), command)

    def test_mutating_probe_rejected(self):
        with self.assertRaises(AuditFailure):
            validate_probe_commands([("bad", "systemctl restart foo")])

    def test_probe_markers_do_not_merge_variable_names(self):
        script = build_probe_script("deadbeefcafe")
        self.assertNotIn("$TOKEN__", script)
        self.assertIn('"__AUDIT_SECTION__"$TOKEN"__"$name', script)
        self.assertIn('"__AUDIT_RC__"$TOKEN"__"$name"__"$rc', script)

    def test_fast_keyboard_supports_launcher(self):
        keyboard = Keyboard(None)
        codes = keyboard._text_scancodes(audit_launcher("deadbeef1234"))
        self.assertTrue(codes)
        self.assertNotIn("base64", audit_launcher("deadbeef1234"))


if __name__ == "__main__":
    unittest.main()
