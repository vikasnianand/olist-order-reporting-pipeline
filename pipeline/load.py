"""
load.py - STEP 3 of the pipeline: build the warehouse and load every table.

Runs sql/schema.sql (creates the star schema + views), then writes:
  - the dimension and fact tables from transform.py
  - the data-quality logs from validate.py
so the dashboard can show both "the business numbers" and "how trustworthy
is this run" on the same connection.

Usage:  python pipeline/load.py
Needs DB_URL set for MySQL; defaults to a local SQLite file for easy testing.
"""
import re

import pandas as pd
from sqlalchemy import create_engine, text

from config import DB_URL, LOG_DIR, SQL_DIR
from transform import transform
from validate import main as run_validation


def split_statements(sql_text):
    """Split schema.sql into individual statements, dropping comment lines."""
    no_comments = re.sub(r"--.*", "", sql_text)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def apply_schema(engine):
    sql_text = (SQL_DIR / "schema.sql").read_text()
    with engine.begin() as conn:
        for stmt in split_statements(sql_text):
            conn.execute(text(stmt))
    print("Schema applied: tables and views created.")


def load_tables(engine, tables):
    with engine.begin() as conn:
        # children before parents don't matter for to_sql's "replace", but keep a sane order for readability
        for name in ["dim_date", "dim_customer", "dim_seller", "dim_product",
                    "fact_orders", "fact_order_items"]:
            tables[name].to_sql(name, conn, if_exists="append", index=False)
            print(f"loaded {name:18s} {len(tables[name]):>6,} rows")


def load_quality_logs(engine):
    check_df = pd.read_csv(LOG_DIR / "quality_report.csv")
    summary_df = pd.read_csv(LOG_DIR / "table_summary.csv")
    with engine.begin() as conn:
        check_df.to_sql("dq_check_log", conn, if_exists="append", index=False)
        summary_df.to_sql("dq_table_summary", conn, if_exists="append", index=False)
    print(f"loaded dq_check_log       {len(check_df):>6,} rows")
    print(f"loaded dq_table_summary   {len(summary_df):>6,} rows")


def main():
    print(f"Connecting to: {DB_URL}\n")
    engine = create_engine(DB_URL)

    print("--- Re-running validation so the logs match this load ---")
    run_validation()

    print("\n--- Applying schema ---")
    apply_schema(engine)

    print("\n--- Transforming ---")
    tables = transform()

    print("\n--- Loading business tables ---")
    load_tables(engine, tables)

    print("\n--- Loading data-quality logs ---")
    load_quality_logs(engine)

    print("\nDone. Warehouse ready for Power BI.")


if __name__ == "__main__":
    main()
