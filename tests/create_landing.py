"""Create deterministic, service-free landing files for the dbt CI build."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'data-generator'))
import generate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "airflow" / "dags"))
from tour_fixture import ROWS, write_landing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--customers', type=int, default=200)
    parser.add_argument('--orders', type=int, default=1000)
    parser.add_argument('--accounts', type=int, default=120)
    args = parser.parse_args()
    anchor = datetime(2026, 1, 31)
    tables = generate.build_full_dataset(generate.SEED, args.customers, args.orders, args.accounts, anchor)
    assert set(tables) == set(generate.RAW_TABLES), 'A landing table is missing'
    assert all(tables.values()), 'The fixture must exercise every source'
    generate.ENVIRONMENT = args.output
    generate.write_exports(tables)
    write_landing(ROWS, args.output)
    for table, rows in tables.items():
        print(f'{table}: {len(rows)} rows')


if __name__ == '__main__':
    main()
