"""Regression checks against Stripe API object semantics (2024-06-20)."""
import csv
import io
import json
import random
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'data-generator'))
import generate
import sources


class StripeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.anchor = datetime(2026, 1, 31, tzinfo=timezone.utc)
        rng = random.Random(17)
        cls.accounts = sources.build_accounts(rng, 250, cls.anchor)
        cls.tables = sources.build_stripe_history(rng, cls.accounts, cls.anchor)

    def test_balance_signs_and_source_links(self):
        charges = {r['charge_id']: json.loads(r['payload']) for r in self.tables['stripe_charges']}
        refunds = {r['refund_id']: json.loads(r['payload']) for r in self.tables['stripe_refunds']}
        for row in self.tables['stripe_balance_transactions']:
            obj = json.loads(row['payload'])
            self.assertEqual(obj['net'], obj['amount'] - obj['fee'])
            source = charges[obj['source']] if obj['type'] == 'charge' else refunds[obj['source']]
            self.assertEqual(obj['created'], source['created'])
            self.assertEqual(obj['currency'], source['currency'])
            self.assertEqual(obj['amount'], source['amount'] * (1 if obj['type'] == 'charge' else -1))
            self.assertEqual(obj['id'], source['balance_transaction'])

    def test_charge_identity_and_refunds(self):
        refunds = self.tables['stripe_refunds']
        totals = {}
        for row in refunds:
            totals[row['charge_id']] = totals.get(row['charge_id'], 0) + int(row['amount'])
        fully_refunded = 0
        for row in self.tables['stripe_charges']:
            obj = json.loads(row['payload'])
            self.assertEqual(row['charge_id'], obj['id'])
            self.assertEqual(obj['amount_refunded'], totals.get(row['charge_id'], 0))
            self.assertLessEqual(obj['amount_refunded'], obj['amount'])
            if obj['status'] == 'succeeded':
                self.assertEqual(obj['refunded'], obj['amount_refunded'] == obj['amount'])
                fully_refunded += obj['refunded']
        self.assertGreater(fully_refunded, 0)

    def test_subscription_snapshot_and_invoice_links(self):
        charges = {r['charge_id']: json.loads(r['payload']) for r in self.tables['stripe_charges']}
        subscriptions = {r['stripe_id']: json.loads(r['payload']) for r in self.tables['stripe_subscriptions']}
        for row in self.tables['stripe_invoices']:
            obj = json.loads(row['payload'])
            self.assertEqual(obj['amount_due'], obj['amount_paid'] + obj['amount_remaining'])
            if obj['paid']:
                self.assertEqual(charges[obj['charge']]['amount'], obj['amount_paid'])
            price = subscriptions[obj['subscription']]['items']['data'][0]['price']
            self.assertEqual(obj['lines']['data'][0]['price']['id'], price['id'])
        for row in self.tables['stripe_subscriptions']:
            obj = json.loads(row['payload'])
            self.assertEqual(generate.parse_timestamp(row['current_period_end']).replace(tzinfo=timezone.utc).timestamp(), obj['current_period_end'])
            self.assertLessEqual(obj['current_period_start'], self.anchor.timestamp())
            if obj['status'] != 'canceled':
                self.assertGreater(obj['current_period_end'], self.anchor.timestamp())
            self.assertEqual(obj['items']['data'][0]['quantity'], 1)

    def test_no_future_created_objects(self):
        for table, rows in self.tables.items():
            for row in rows:
                obj = json.loads(row['payload'])
                self.assertLessEqual(obj['created'], self.anchor.timestamp(), (table, obj['id']))

    def test_live_charges_keep_customer_identity(self):
        account = dict(self.accounts[0], stripe_customer_id='cus_existing')
        rows = generate._recent_charges(random.Random(10), [account], self.anchor, 20, 1)
        for row in rows['stripe_charges']:
            obj = json.loads(row['payload'])
            self.assertEqual(obj['customer'], 'cus_existing')
            self.assertNotIn('invoice', obj['metadata'])
        self.assertEqual(generate._recent_charges(random.Random(10), [], self.anchor, 20, 1), {})

    def test_csv_round_trip_matches_parquet(self):
        import pyarrow.parquet as pq
        previous = generate.ENVIRONMENT
        with tempfile.TemporaryDirectory() as directory:
            try:
                generate.ENVIRONMENT = Path(directory)
                generate.write_exports({'stripe_customers': self.tables['stripe_customers'][:2]})
                path = Path(directory) / 'stripe_customers'
                csv_rows = list(csv.DictReader(io.StringIO(path.with_suffix('.csv').read_text())))
                parquet_rows = pq.read_table(path.with_suffix('.parquet')).to_pylist()
                self.assertEqual(csv_rows, parquet_rows)
                json.loads(csv_rows[0]['payload'])
            finally:
                generate.ENVIRONMENT = previous


if __name__ == '__main__':
    unittest.main()
