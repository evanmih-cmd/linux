"""Installation release audit must never confuse owner USB with project scope."""
import unittest
from config import Config
from release_readiness import review
from workflow import install_contract_check


class ReleaseReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = Config()
        cls.contract = install_contract_check(cls.cfg)
        cls.iso = {"verified": True, "sha256": cls.cfg.official_iso_sha256}

    def test_owner_creates_usb_not_blocker_but_unsafe_target_is(self):
        audit = {"status": "FAIL", "failed": ["bitlocker-vm-flow"],
                 "checks": [{"name": "bitlocker-vm-flow", "status": "FAIL"}],
                 "facts": {"AuditContext": {"IsElevated": True}}}
        result = review(audit, contract=self.contract,
                        iso=self.iso, cfg=self.cfg)
        self.assertEqual(result["status"], "NO_GO")
        self.assertTrue(result["owner_prepares_bootable_usb"])
        self.assertFalse(result["owner_usb_image_creation_is_project_blocker"])
        self.assertNotIn("bootable-official-usb-with-physical-answer-file",
                         result["blockers"])
        self.assertEqual(len(result["requirements"]), 36)
        self.assertIn("microsoft-winre-after-windows-and-lun-growth-validation",
                      result["preinstall_blockers"])
        self.assertIn("owner-startup-pin-removes-tpm-only-bypass",
                      result["postinstall_acceptance_blockers"])
        self.assertIn("interactive-raid-disk-selection-and-ssd1-offline",
                      result["blockers"])
        self.assertIn("microsoft-winre-after-windows-and-lun-growth-validation",
                      result["blockers"])
        self.assertEqual(next(x["status"] for x in result["checks"]
                              if x["gate"] == "requirements-1-to-36-traceable"),
                         "PASS")

    def test_requirement_coverage_is_not_fabricated_acceptance_evidence(self):
        audit = {"status": "FAIL", "failed": ["administrator-protection"],
                 "checks": [], "facts": {"AuditContext": {"IsElevated": True}}}
        result = review(audit, contract=self.contract,
                        iso=self.iso, cfg=self.cfg)
        self.assertIn("safe-production-installer-staging", result["blockers"])
        self.assertTrue({1, 3, 28}.issubset(
            set(result["requirements_without_real_evidence"])
        ))
        self.assertEqual(
            next(x["status"] for x in result["requirements"] if x["id"] == 1),
            "NOT_ASSESSED"
        )
        self.assertEqual(sum(result["requirements_summary"].values()), 36)

    def test_not_real_administrator_audit_must_fail(self):
        audit = {"status": "PASS", "failed": [],
                 "checks": [], "facts": {"AuditContext": {"IsElevated": False}}}
        result = review(audit, contract=self.contract,
                        iso=self.iso, cfg=self.cfg)
        self.assertIn("real-elevated-vm-security-audit", result["blockers"])

    def test_iso_hash_mismatch_must_fail_closed(self):
        audit = {"status": "PASS", "failed": [],
                 "checks": [], "facts": {"AuditContext": {"IsElevated": True}}}
        result = review(audit, contract=self.contract,
                        iso={"verified": True, "sha256": "0"*64}, cfg=self.cfg)
        self.assertIn("official-microsoft-iso-sha256", result["blockers"])

    def test_every_release_gate_maps_to_business_requirement(self):
        audit = {"status": "FAIL", "failed": ["administrator-protection"],
                 "checks": [{"name": "administrator-protection", "status": "FAIL"}],
                 "facts": {"AuditContext": {"IsElevated": True}}}
        result = review(audit, contract=self.contract,
                        iso=self.iso, cfg=self.cfg)
        covered = set()
        for x in result["checks"]:
            self.assertTrue(x["business_requirements"], x["gate"])
            self.assertTrue(all(1 <= k <= 36 for k in x["business_requirements"]))
            covered.update(x["business_requirements"])
        self.assertEqual(covered, set(range(1, 37)))


if __name__ == "__main__":
    unittest.main()
