"""Verify the developer investigation against the same fixture and model SQL."""
import sys
import unittest
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "airflow" / "dags"))
from tour_fixture import ROWS


class TourRegressionTest(unittest.TestCase):
    def test_source_bug_and_corrected_predicate(self):
        with duckdb.connect() as database:
            database.execute("create schema landing")
            database.execute("create table landing.demo_tour_orders(order_id varchar, ordered_on date, status varchar, amount integer)")
            database.executemany("insert into landing.demo_tour_orders values (?,?,?,?)", ROWS)
            model = (ROOT / "dbt/models/marts/fct_tour_orders.sql").read_text().replace("{{ source('tour_landing', 'demo_tour_orders') }}", "landing.demo_tour_orders")
            database.execute("create view report as " + model)
            original = database.execute("select d.ordered_on,count(r.order_id),coalesce(sum(r.amount),0) from (select distinct ordered_on from landing.demo_tour_orders) d left join report r using(ordered_on) group by d.ordered_on order by d.ordered_on").fetchall()
            self.assertEqual([(row[1], row[2]) for row in original], [(3, 300), (1, 90), (0, 0)])
            corrected = database.execute("select ordered_on,count(*),sum(amount) from landing.demo_tour_orders where status in ('paid','completed') group by ordered_on order by ordered_on").fetchall()
            self.assertEqual([(row[1], row[2]) for row in corrected], [(3, 300)] * 3)
            self.assertEqual(len({row[0] for row in ROWS}), 9)


if __name__ == "__main__":
    unittest.main()
