import unittest

from audit import evaluate, WALLET_EXTENSION_IDS


def good_facts():
    return {
        "AuditContext": {"IsElevated": True, "User": "WINBENCH\\vmbench"},
        "OS": {
            "Caption": "Microsoft Windows 11 Pro",
            "OSArchitecture": "64-bit",
        },
        "Locale": {
            "Culture": "de-DE",
            "UICulture": "en-US",
            "HomeLocationGeoId": 94,
            "TimeZoneId": "W. Europe Standard Time",
            "UserLanguages": [
                {"LanguageTag": "en-US", "InputMethodTips": ["0409:00000409"]},
                {"LanguageTag": "ru-RU", "InputMethodTips": ["0419:00000419"]},
            ],
            "KeyboardPreload": ["00000409", "00000419"],
        },
        "SecureBoot": True,
        "TPM": {
            "TpmPresent": True,
            "TpmReady": True,
            "TpmEnabled": True,
            "TpmActivated": True,
            "SpecVersion": "2.0, 0, 1.38",
            "ManufacturerIdTxt": "VBOX",
        },
        "Defender": {
            "AntivirusEnabled": True,
            "RealTimeProtectionEnabled": True,
        },
        "Firewall": [
            {"Name": "Domain", "Enabled": True},
            {"Name": "Private", "Enabled": True},
            {"Name": "Public", "Enabled": True},
        ],
        "Disks": [
            {
                "Number": 0,
                "IsSystem": True,
                "PartitionStyle": "GPT",
            }
        ],
        "Partitions": [
            {"DiskNumber": 0, "PartitionNumber": 1, "DriveLetter": "",
             "GptType": "{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}",
             "Size": 300*1024**2, "Type": "System"},
            {"DiskNumber": 0, "PartitionNumber": 2, "DriveLetter": "",
             "GptType": "{e3c9e316-0b5c-4db8-817d-f92df00215ae}",
             "Size": 16*1024**2, "Type": "Reserved"},
            {"DiskNumber": 0, "PartitionNumber": 3, "DriveLetter": "C",
             "GptType": "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}",
             "Size": 100533272576, "Type": "Basic"},
            {"DiskNumber": 0, "PartitionNumber": 4, "DriveLetter": "",
             "GptType": "{de94bba4-06d1-4d40-a16a-bfd50179d6ac}",
             "Size": 2048*1024**2, "Type": "Recovery"},
        ],
        "WinRE": "Windows RE status: Enabled\\r\\nWindows RE location: \\\\?\\GLOBALROOT\\device\\harddisk0\\partition4\\Recovery\\WindowsRE",
        "Chrome": {"Installed": True, "Version": "1"},
        "Edge": {"Installed": True, "Version": "1"},
        "PowerShell7": {"Installed": True, "Method": "MSIX", "Version": "7.6.6.0"},
        "KeePass": {"Installed": True, "Version": "2.61.1.0"},
        "LedgerWallet": {"Installed": True, "Version": "4.23.0.0"},
        "OwnerProfile": {
            "Name": "owner",
            "SID": "S-1-5-21-11-22-33-1001",
            "Path": r"C:\Users\owner",
            "Loaded": True,
            "Resolved": True,
        },
        "ChromePolicy": {
            "ValidJson": True,
            "Ids": ["*", *sorted(WALLET_EXTENSION_IDS)],
            "DefaultMode": "blocked",
        },
        "WalletExtensions": [
            {"Id":identifier, "Installed": True, "FromWebStore": True,
             "ActivePermissions": True, "DisableReasons": [],
             "InstallLocation": 6, "Name": "Store wallet", "Versions": ["1.0_0"]}
            for identifier in sorted(WALLET_EXTENSION_IDS)
        ],
        "OtherChromeExtensionIds": [],
        "BitLockerPolicy": {"UseAdvancedStartup": 1, "EnableBDEWithNoTPM": 0, "UseTPM": 2, "UseTPMPIN": 2, "UseTPMKey": 0, "UseTPMKeyPIN": 0, "MinimumPIN": 8},
        "SandboxFeature": {"Name": "Containers-DisposableClientVM", "State": "Enabled"},
        "BitLocker": {"VolumeStatus": "FullyEncrypted", "ProtectionStatus": "On", "KeyProtectorTypes": ["TpmPin", "RecoveryPassword"]},
        "DeviceGuard": {
            "VirtualizationBasedSecurityStatus": 0,
            "SecurityServicesRunning": [],
            "SecurityServicesConfigured": [2],
        },
        "DeviceGuardPolicy": {"EnableVBS": 1, "RequirePlatformSecurityFeatures": 1,
                              "VBSLocked": 0, "HVCIEnabled": 1, "HVCILocked": 0},
        "AdministratorProtection": {
            "EnableLUA": 1,
            "TypeOfAdminApprovalMode": 2,
        },
    }


class AuditTests(unittest.TestCase):
    def test_vm_good_baseline_passes_with_hardware_not_provable(self):
        result = evaluate(good_facts())
        self.assertEqual(result["status"], "PASS", result)
        self.assertIn("ess-face", result["not_provable_in_vm"])
        self.assertNotIn("bitlocker-vm-flow", result["warnings"])
        self.assertEqual(result["warnings"], [])

    def test_default_windows_partition_sizes_not_hardcoded(self):
        fixture = good_facts()
        fixture["Partitions"][0]["Size"] = 260 * 1024**2
        fixture["Partitions"][3]["Size"] = 900 * 1024**2
        result = evaluate(fixture)
        self.assertNotIn("vm-independent-gpt-partitions", result["failed"])

    def test_recovery_partition_number_is_measured_not_assumed(self):
        fixture = good_facts()
        fixture["Partitions"][3]["PartitionNumber"] = 5
        fixture["WinRE"] = fixture["WinRE"].replace("partition4", "partition5")
        result = evaluate(fixture)
        self.assertNotIn("vm-independent-gpt-partitions", result["failed"])
        self.assertNotIn("winre-on-target-recovery", result["failed"])

    def test_winre_must_be_on_target_even_if_sizes_are_valid(self):
        fixture = good_facts()
        fixture["WinRE"] = fixture["WinRE"].replace("harddisk0", "harddisk1")
        result = evaluate(fixture)
        self.assertIn("winre-on-target-recovery", result["failed"])

    def test_common_policy_audit_allows_separate_hardware_locks(self):
        fixture = good_facts()
        fixture["DeviceGuardPolicy"]["VBSLocked"] = 1
        fixture["DeviceGuardPolicy"]["HVCILocked"] = 1
        result = evaluate(fixture)
        self.assertNotIn("vbs-boot-policy", result["failed"])
        self.assertNotIn("hvci-boot-policy", result["failed"])

    def test_non_elevated_audit_never_passes(self):
        fixture = good_facts()
        fixture["AuditContext"]["IsElevated"] = False
        result = evaluate(fixture)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("audit-elevated", result["failed"])

    def test_privileged_gates_fail_when_unconfigured(self):
        fixture = good_facts()
        fixture["SecureBoot"] = None
        fixture["TPM"]["TpmReady"] = False
        fixture["WinRE"] = None
        fixture["BitLocker"]["ProtectionStatus"] = "Off"
        fixture["BitLocker"]["KeyProtectorTypes"] = []
        fixture["AdministratorProtection"]["TypeOfAdminApprovalMode"] = 1
        result = evaluate(fixture)
        self.assertEqual(result["status"], "FAIL")
        for name in ("secure-boot", "tpm2-visible-ready", "winre-enabled",
                     "bitlocker-vm-flow", "administrator-protection"):
            self.assertIn(name, result["failed"])
            self.assertNotIn(name, result["warnings"])

    def test_vm_gpt_layout_and_vbs_policy_fail_closed(self):
        fixture = good_facts()
        fixture["Partitions"][3]["GptType"] = "{00000000-0000-0000-0000-000000000000}"
        fixture["DeviceGuardPolicy"]["HVCIEnabled"] = 0
        result = evaluate(fixture)
        self.assertIn("vm-independent-gpt-partitions", result["failed"])
        self.assertIn("hvci-boot-policy", result["failed"])

    def test_tpm_only_is_interim_not_final(self):
        fixture = good_facts()
        fixture["BitLocker"]["KeyProtectorTypes"] = ["Tpm", "RecoveryPassword"]
        result = evaluate(fixture)
        self.assertEqual(next(c["status"] for c in result["checks"] if c["name"] == "bitlocker-tpm-immediate-protection"), "PASS")
        self.assertIn("bitlocker-vm-flow", result["failed"])

    def test_sandbox_feature_must_be_present(self):
        fixture = good_facts()
        fixture["SandboxFeature"]["State"] = "Disabled"
        self.assertIn("windows-sandbox-feature", evaluate(fixture)["failed"])

    def test_audit_rejects_temporary_admin_profile_misattribution(self):
        fixture = good_facts()
        fixture["OwnerProfile"]["Name"] = "ADMIN_owner"
        fixture["OwnerProfile"]["Path"] = r"C:\Users\ADMIN_owner"
        result = evaluate(fixture)
        for name in ("owner-profile-target", "powershell7-installed", "chrome-wallets-verified-six"):
            self.assertIn(name, result["failed"])

    def test_audit_rejects_missing_owner_identity(self):
        fixture = good_facts()
        fixture.pop("OwnerProfile")
        result = evaluate(fixture)
        for name in ("owner-profile-target", "powershell7-installed", "chrome-wallets-verified-six"):
            self.assertIn(name, result["failed"])

    def test_missing_powershell7_fails(self):
        fixture = good_facts()
        fixture["PowerShell7"] = {"Installed": False}
        result = evaluate(fixture)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("powershell7-installed", result["failed"])

    def test_missing_wallet_or_untrusted_extension_fails(self):
        for mutation in ("missing", "untrusted", "disabled", "unexpected"):
            with self.subTest(mutation=mutation):
                fixture = good_facts()
                if mutation == "missing":
                    fixture["WalletExtensions"].pop()
                elif mutation == "untrusted":
                    fixture["WalletExtensions"][0]["FromWebStore"] = False
                elif mutation == "disabled":
                    fixture["WalletExtensions"][0]["DisableReasons"] = [1]
                else:
                    fixture["OtherChromeExtensionIds"] = ["lookalikeextension"]
                result = evaluate(fixture)
                self.assertIn("chrome-wallets-verified-six", result["failed"])

    def test_missing_keepass_or_ledger_fails(self):
        for field, check in (("KeePass", "keepass2-installed"),
                             ("LedgerWallet", "ledger-wallet-desktop")):
            with self.subTest(field=field):
                fixture = good_facts()
                fixture[field]["Installed"] = False
                self.assertIn(check, evaluate(fixture)["failed"])

    def test_n_edition_fails(self):
        fixture = good_facts()
        fixture["OS"]["Caption"] = "Microsoft Windows 11 Pro N"
        result = evaluate(fixture)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("windows-11-pro", result["failed"])

    def test_security_baseline_failures_are_real_failures(self):
        fixture = good_facts()
        fixture["SecureBoot"] = False
        fixture["Defender"]["RealTimeProtectionEnabled"] = False
        result = evaluate(fixture)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("secure-boot", result["failed"])
        self.assertIn("defender-realtime", result["failed"])

    def test_german_keyboard_is_a_hard_failure(self):
        fixture = good_facts()
        fixture["Locale"]["UserLanguages"].append(
            {"LanguageTag": "de-DE", "InputMethodTips": ["0407:00000407"]}
        )
        fixture["Locale"]["KeyboardPreload"].append("00000407")
        result = evaluate(fixture)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("keyboard-layouts-us-russian-only", result["failed"])


if __name__ == "__main__":
    unittest.main()
