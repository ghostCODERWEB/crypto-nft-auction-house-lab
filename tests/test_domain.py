import unittest, copy, json
from decimal import Decimal
from pathlib import Path
from cryptolab import analyze
from cryptolab.engine import *

EXAMPLE = json.loads(Path("examples/input.json").read_text())


class DomainTests(unittest.TestCase):
    def test_royalty_settlement(self):
        r = analyze(EXAMPLE)
        self.assertEqual(r["balances"]["artist"], 15)
        self.assertEqual(r["balances"]["seller"], 278)
        self.assertEqual(r["nft_owners"]["nft1"], "bob")

    def test_extension(self):
        self.assertEqual(analyze(EXAMPLE)["auctions"]["auction1"]["end"], 24)

    def test_pull_refund(self):
        self.assertEqual(analyze(EXAMPLE)["balances"]["alice"], 1000)

    def test_early_settle(self):
        d = copy.deepcopy(EXAMPLE)
        d["events"][-1]["timestamp"] = 23
        with self.assertRaises(ValueError):
            analyze(d)

    def test_invalid_owner(self):
        d = copy.deepcopy(EXAMPLE)
        d["events"][0]["seller"] = "bob"
        with self.assertRaises(ValueError):
            analyze(d)
