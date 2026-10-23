"""SessionAffinity persistence: a restart must not cold-start live conversations.

The prefix cache lives upstream, keyed by the account that built it. Bindings
used to be memory-only, so every restart sent each live conversation to a
possibly different account and paid a full re-prefill (a 180k-token context
costs 10-15s once). These tests pin the opt-in persistence layer:

* without `state_path` nothing is written (old behaviour, tests, short pools),
* with it, bindings survive a fresh object,
* expired entries are dropped on load,
* a corrupt or unreadable file is treated as empty (dispatch must not break),
* the pool wires the file in and keeps it out of the account scan.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wb_accounts


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "affinity.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_memory_only_by_default(self):
        affinity = wb_accounts.SessionAffinity()
        affinity.bind("pfx-a", "uid1")
        self.assertEqual(affinity.get("pfx-a"), "uid1")
        self.assertEqual(os.listdir(self.dir), [])

    def test_bindings_survive_a_restart(self):
        first = wb_accounts.SessionAffinity(state_path=self.path, flush_interval=0)
        first.bind("pfx-a", "uid1")
        first.bind("pfx-a", "uid2")
        first.flush()

        second = wb_accounts.SessionAffinity(state_path=self.path)
        self.assertEqual(second.get("pfx-a"), "uid2")
        self.assertEqual(second.recent("pfx-a"), ["uid2", "uid1"])

    def test_expired_entries_are_dropped_on_load(self):
        first = wb_accounts.SessionAffinity(state_path=self.path,
                                            ttl=0.05, flush_interval=0)
        first.bind("pfx-a", "uid1")
        first.flush()
        time.sleep(0.08)

        second = wb_accounts.SessionAffinity(state_path=self.path)
        self.assertEqual(second.recent("pfx-a"), [])
        self.assertIsNone(second.get("pfx-a"))

    def test_corrupt_file_is_treated_as_empty(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        affinity = wb_accounts.SessionAffinity(state_path=self.path)
        self.assertEqual(affinity.recent("pfx-a"), [])
        # ... and it must still be usable afterwards.
        affinity.bind("pfx-a", "uid1")
        self.assertEqual(affinity.get("pfx-a"), "uid1")

    def test_malformed_entries_are_skipped(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({
                "pfx-good": [["uid1", time.time() + 60]],
                "pfx-bad": [["uid2"], "nope", [3, time.time() + 60], None],
                "pfx-wrong-type": "not-a-list",
                42: [["uid3", time.time() + 60]],
            }, fh)
        affinity = wb_accounts.SessionAffinity(state_path=self.path)
        self.assertEqual(affinity.recent("pfx-good"), ["uid1"])
        self.assertEqual(affinity.recent("pfx-bad"), [])
        self.assertEqual(affinity.recent("pfx-wrong-type"), [])

    def test_history_cap_is_applied_on_load(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"pfx-a": [["u%d" % i, time.time() + 60] for i in range(9)]}, fh)
        affinity = wb_accounts.SessionAffinity(state_path=self.path, history=3)
        self.assertEqual(affinity.recent("pfx-a"), ["u0", "u1", "u2"])

    def test_interval_batches_writes(self):
        affinity = wb_accounts.SessionAffinity(state_path=self.path,
                                               flush_interval=3600)
        affinity.bind("pfx-a", "uid1")
        # The first bind is suppressed by the interval, so the file may be
        # absent; an explicit flush must still write it.
        affinity.flush()
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["pfx-a"][0][0], "uid1")

    def test_unbind_is_persisted(self):
        first = wb_accounts.SessionAffinity(state_path=self.path, flush_interval=0)
        first.bind("pfx-a", "uid1")
        first.unbind("pfx-a")
        second = wb_accounts.SessionAffinity(state_path=self.path)
        self.assertEqual(second.recent("pfx-a"), [])

    def test_pool_wires_the_state_file(self):
        pool = wb_accounts.AccountPool(self.dir)
        self.assertTrue(pool.affinity.state_path.endswith("affinity.json"))
        self.assertEqual(os.path.dirname(pool.affinity.state_path), self.dir)

    def test_state_file_is_not_read_as_an_account(self):
        # A file in the account directory that is not a credential must be
        # skipped, or every restart logs a bogus "unreadable account" error.
        self.assertIn(wb_accounts.AFFINITY_STATE_FILE, wb_accounts.NON_ACCOUNT_FILES)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"pfx-a": [["uid1", time.time() + 60]]}, fh)
        pool = wb_accounts.AccountPool(self.dir)
        pool.load()
        self.assertEqual(pool.accounts, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
