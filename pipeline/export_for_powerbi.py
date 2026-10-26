"""
export_for_powerbi.py - turns your warehouse into ONE Excel file for Power BI.

Why this exists: Power BI Desktop doesn't run on Mac. Power BI Service (the
browser version at app.powerbi.com) can't connect to a local SQLite file
directly, but it CAN import an Excel workbook. So this script reads every
report-ready view from your warehouse and writes each one onto its own sheet
in a single .xlsx file, ready to upload.

Usage:  python pipeline/export_for_powerbi.py
Needs load.py to have been run first (the warehouse must already exist).
"""
import pandas as pd
from sqlalchemy import create_engine

from config import DB_URL, ROOT

# One sheet per view. Sheet names must stay under 31 characters (Excel's limit).
VIEWS = {
    "KPI Monthly": "vw_kpi_monthly",
    "Order Performance": "vw_order_performance",
    "Seller Performance": "vw_seller_performance",
    "Category Performance": "vw_category_performance",
    "State Performance": "vw_state_performance",
    "Data Quality": "vw_data_quality",
}

OUTPUT_FILE = ROOT / "data" / "olist_dashboard_data.xlsx"


def main():
    print(f"Connecting to: {DB_URL}")
    engine = create_engine(DB_URL)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        for sheet_name, view_name in VIEWS.items():
            df = pd.read_sql(f"SELECT * FROM {view_name}", engine)
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  {sheet_name:22s} {len(df):>7,} rows  <- {view_name}")

    print(f"\nDone. Upload this file to Power BI: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
