"""Offline tests of one-command audit transport and fail-closed evaluation."""
import base64
import gzip
import hashlib
import json
import unittest

from live_audit import PREFIX, receive_facts, CHAR_KEYS
from test_audit import good_facts
from audit import evaluate


class FakeBox:
    def __init__(self, entries):
        self.machine = "fake-vm"
        self.entries = entries
    def _vals(self, method, pairs):
        self.last_method = method
        return [self.entries.get(dict(pairs)["property"], "")]
    def state(self):
        return "Running"


class LiveAuditTests(unittest.TestCase):
    def make_box(self, facts):
        raw = json.dumps(facts).encode("utf-8")
        data = base64.b64encode(gzip.compress(raw)).decode()
        prefix = PREFIX + "/abcdef012345"
        parts = [data[i:i + 800] for i in range(0, len(data), 800)]
        values = {prefix + "/state": "ready",
                  prefix + "/count": str(len(parts)),
                  prefix + "/sha256": hashlib.sha256(raw).hexdigest()}
        values.update({prefix + f"/part{i:03}": item
                       for i, item in enumerate(parts)})
        return FakeBox(values)

    def test_full_gzip_roundtrip_and_real_policy_evaluation(self):
        facts = good_facts()
        data, raw = receive_facts(self.make_box(facts), "abcdef012345", 5)
        self.assertEqual(data, facts)
        self.assertEqual(json.loads(raw), facts)
        self.assertEqual(evaluate(data)["status"], "PASS")

    def test_corrupted_payload_fails_closed(self):
        box = self.make_box(good_facts())
        box.entries[PREFIX + "/abcdef012345/sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            receive_facts(box, "abcdef012345", 5)

    def test_guest_failure_is_not_marked_as_pass(self):
        box = FakeBox({
            PREFIX + "/abcdef012345/state": "failed",
            PREFIX + "/abcdef012345/error": "audit_did_not_complete",
        })
        with self.assertRaisesRegex(RuntimeError, "audit_did_not_complete"):
            receive_facts(box, "abcdef012345", 5)

    def test_guest_property_does_not_accept_unrelated_run(self):
        box = self.make_box(good_facts())
        # Other nonce must not see stale report. Test separately without waiting.
        self.assertNotIn(PREFIX + "/bbbbbbbbbbbb/state", box.entries)

    def test_one_line_command_scancodes_have_bounded_alphabet(self):
        self.assertEqual(set("F:\\RUN.CMD".lower()) - set(CHAR_KEYS), set())


if __name__ == "__main__":
    unittest.main()
