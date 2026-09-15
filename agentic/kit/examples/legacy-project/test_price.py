import unittest
from price import total_cents


class PriceTests(unittest.TestCase):
    def test_one_shipping_charge_per_order(self):
        self.assertEqual(total_cents(250, 2), 600)

    def test_single_item_keeps_existing_behavior(self):
        self.assertEqual(total_cents(250, 1), 350)
