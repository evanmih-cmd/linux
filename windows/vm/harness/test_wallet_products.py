import json
import re
import unittest
from pathlib import Path
import yaml

CONFIG = Path(__file__).resolve().parents[2] / "configuration" / "workstation.winget"
WALLETS = {
    "MetaMask": "nkbihfbeogaeaoehlefnkodbefgpgknn",
    "Phantom": "bfnaelmomeimhlpmgjnjophhpkkoljpa",
    "Rabby": "acmacodkjbdgmoleebolmdjonilkdbch",
    "Trust Wallet": "egjidjbpglichdcondbcbdnbeeppgdph",
    "Backpack": "aflkmfhebedbjioipglgcbcmnbpgliof",
    "Zerion": "klghhnkeealcohjjanjjdaeeggmfmlpl",
}
GOOGLE_UPDATE = "https://clients2.google.com/service/update2/crx"


class WalletProductBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = yaml.safe_load(CONFIG.read_text())
        cls.resources = {
            r["name"]: r
            for r in cls.manifest["resources"]
        }

    def test_official_packages_exact(self):
        ids = {
            r["properties"].get("id")
            for r in self.resources.values()
            if r["type"] == "Microsoft.WinGet/Package"
        }
        self.assertIn("DominikReichl.KeePass", ids)
        self.assertIn("LedgerHQ.LedgerLive", ids)

    def test_wallet_extension_policy_is_exact_and_vetted(self):
        r = self.resources["ChromeWalletExtensionSettings"]
        self.assertEqual(r["type"], "Microsoft.Windows/RegistryList")
        self.assertEqual(len(r["properties"]["registryEntries"]), 1)
        entry = r["properties"]["registryEntries"][0]
        self.assertEqual(entry["keyPath"], r"HKLM\SOFTWARE\Policies\Google\Chrome")
        self.assertEqual(entry["valueName"], "ExtensionSettings")
        self.assertEqual(r["metadata"]["winget"]["securityContext"], "elevated")
        policy = json.loads(entry["valueData"]["String"])
        self.assertEqual(set(policy), set(WALLETS.values()) | {"*"})
        self.assertEqual(policy["*"], {"installation_mode": "blocked"})
        for identifier in WALLETS.values():
            self.assertRegex(identifier, r"^[a-p]{32}$")
            self.assertEqual(policy[identifier], {
                "installation_mode": "normal_installed",
                "update_url": GOOGLE_UPDATE,
            })

    def test_no_crx_mirrors_or_scripts(self):
        config = CONFIG.read_text()
        self.assertNotIn("http://", config)
        self.assertNotIn("force_installed", yaml.safe_load(CONFIG.read_text())["resources"][
            next(i for i, r in enumerate(self.manifest["resources"]) if r["name"] == "ChromeWalletExtensionSettings")
        ]["properties"]["registryEntries"][0]["valueData"]["String"])
        self.assertNotIn("RunCommandOnSet", config)
        self.assertNotIn("Invoke-WebRequest", config)


if __name__ == "__main__":
    unittest.main()
