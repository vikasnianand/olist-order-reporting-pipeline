"""
validate.py - STEP 1 of the pipeline: check the raw data before anyone uses it.

The idea: a manager should never see a number built on bad data. So every raw
table goes through a list of checks. Each check looks for one kind of problem.

  - severity "error"   -> the row is REJECTED (moved to data/rejected/ with the reason)
  - severity "warning" -> the row is KEPT, but the problem is counted in the report

Everything that is checked, caught or kept is written to logs/, and later loaded
into the warehouse so the dashboard can show a "data quality" page.

Usage:  python pipeline/validate.py
"""
from datetime import datetime

import pandas as pd

from config import (CLEAN_DIR, LOG_DIR, MAX_VALID_DATE, MIN_VALID_DATE, RAW_DIR,
                    RAW_FILES, REJECTED_DIR)

CHECK_LOG = []      # one entry per check (what we looked for, how many rows failed)
TABLE_SUMMARY = []  # one entry per table (rows in / clean / rejected)


def load_raw():
    """Read every raw CSV into a DataFrame, exactly as it arrived."""
    missing = [f for f in RAW_FILES.values() if not (RAW_DIR / f).exists()]
    if missing:
        raise FileNotFoundError(
            "These files are missing from data/raw/: " + ", ".join(missing) +
            "\nPut the Olist CSVs there, or run: python pipeline/generate_sample_data.py")
    return {key: pd.read_csv(RAW_DIR / fname) for key, fname in RAW_FILES.items()}


def run_checks(table, df, checks):
    """
    Apply a list of checks to one table.
    Each check is (name, severity, description, mask). 'mask' is True for rows that FAIL.
    Returns (clean_rows, rejected_rows).
    """
    reasons = pd.Series("", index=df.index, dtype="object")  # why each row was rejected
    for name, severity, description, mask in checks:
        mask = mask.fillna(False).astype(bool)
        CHECK_LOG.append({
            "table_name": table, "check_name": name, "severity": severity,
            "description": description, "rows_checked": len(df), "rows_failed": int(mask.sum()),
        })
        if severity == "error":
            reasons[mask] = reasons[mask] + name + "; "

    rejected_mask = reasons != ""
    clean = df[~rejected_mask].copy()
    rejected = df[rejected_mask].copy()
    rejected["reject_reason"] = reasons[rejected_mask].str.rstrip("; ")

    TABLE_SUMMARY.append({
        "table_name": table, "rows_in": len(df),
        "rows_clean": len(clean), "rows_rejected": len(rejected),
    })
    return clean, rejected


def to_dt(series):
    """Turn text into real dates. Anything unreadable becomes NaT (a blank date) instead of crashing."""
    return pd.to_datetime(series, errors="coerce")


def validate_all(raw):
    clean, rejected = {}, {}
    lo, hi = pd.Timestamp(MIN_VALID_DATE), pd.Timestamp(MAX_VALID_DATE)

    # ---------- customers ----------
    df = raw["customers"]
    clean["customers"], rejected["customers"] = run_checks("customers", df, [
        ("duplicate_customer_id", "error", "Same customer_id appears more than once",
         df.duplicated("customer_id", keep="first")),
        ("missing_customer_id", "error", "customer_id is blank", df["customer_id"].isna()),
    ])

    # ---------- sellers ----------
    df = raw["sellers"]
    clean["sellers"], rejected["sellers"] = run_checks("sellers", df, [
        ("duplicate_seller_id", "error", "Same seller_id appears more than once",
         df.duplicated("seller_id", keep="first")),
        ("missing_seller_id", "error", "seller_id is blank", df["seller_id"].isna()),
    ])

    # ---------- products ----------
    df = raw["products"]
    clean["products"], rejected["products"] = run_checks("products", df, [
        ("duplicate_product_id", "error", "Same product_id appears more than once",
         df.duplicated("product_id", keep="first")),
        ("missing_category", "warning", "Product has no category (kept, shown as 'unknown')",
         df["product_category_name"].isna()),
        ("non_positive_weight", "warning", "Product weight is zero or negative",
         df["product_weight_g"] <= 0),
    ])

    clean["category_translation"] = raw["category_translation"].drop_duplicates("product_category_name")

    # ---------- orders ----------
    df = raw["orders"].copy()
    purchase = to_dt(df["order_purchase_timestamp"])
    approved = to_dt(df["order_approved_at"])
    carrier = to_dt(df["order_delivered_carrier_date"])
    delivered = to_dt(df["order_delivered_customer_date"])
    clean["orders"], rejected["orders"] = run_checks("orders", df, [
        ("duplicate_order_id", "error", "Same order_id appears more than once (first copy kept)",
         df.duplicated("order_id", keep="first")),
        ("customer_not_found", "error", "Order points to a customer that does not exist",
         ~df["customer_id"].isin(clean["customers"]["customer_id"])),
        ("purchase_date_invalid", "error", "Purchase date missing, unreadable or outside valid range",
         purchase.isna() | (purchase < lo) | (purchase > hi)),
        ("approved_before_purchase", "error", "Order approved before it was placed",
         approved < purchase),
        ("delivered_before_purchase", "error", "Delivered before it was purchased (impossible)",
         delivered < purchase),
        ("delivered_without_date", "error", "Status is 'delivered' but there is no delivery date",
         df["order_status"].eq("delivered") & delivered.isna()),
        ("carrier_before_approval", "warning", "Handed to carrier before it was approved (kept)",
         carrier < approved),
    ])

    valid_orders = clean["orders"]["order_id"]

    # ---------- order items ----------
    df = raw["items"]
    clean["items"], rejected["items"] = run_checks("items", df, [
        ("duplicate_item_row", "error", "Same order_id + order_item_id appears twice",
         df.duplicated(["order_id", "order_item_id"], keep="first")),
        ("order_not_in_clean_orders", "error", "Item belongs to an order that is missing or was rejected",
         ~df["order_id"].isin(valid_orders)),
        ("product_not_found", "error", "Item points to a product that does not exist",
         ~df["product_id"].isin(clean["products"]["product_id"])),
        ("seller_not_found", "error", "Item points to a seller that does not exist",
         ~df["seller_id"].isin(clean["sellers"]["seller_id"])),
        ("price_not_positive", "error", "Price is zero or negative", df["price"] <= 0),
        ("freight_negative", "error", "Freight cost is negative", df["freight_value"] < 0),
    ])

    # ---------- payments ----------
    df = raw["payments"]
    clean["payments"], rejected["payments"] = run_checks("payments", df, [
        ("order_not_in_clean_orders", "error", "Payment belongs to an order that is missing or was rejected",
         ~df["order_id"].isin(valid_orders)),
        ("payment_negative", "error", "Payment value is negative", df["payment_value"] < 0),
        ("payment_zero", "warning", "Payment value is zero (often a voucher, kept)",
         df["payment_value"] == 0),
    ])

    # ---------- reviews ----------
    df = raw["reviews"]
    clean["reviews"], rejected["reviews"] = run_checks("reviews", df, [
        ("duplicate_review", "error", "Same review_id + order_id appears twice",
         df.duplicated(["review_id", "order_id"], keep="first")),
        ("order_not_in_clean_orders", "error", "Review belongs to an order that is missing or was rejected",
         ~df["order_id"].isin(valid_orders)),
        ("score_out_of_range", "error", "Review score is not between 1 and 5",
         ~df["review_score"].between(1, 5)),
    ])

    return clean, rejected


def save_outputs(clean, rejected):
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for name, df in clean.items():
        df.to_csv(CLEAN_DIR / f"{name}_clean.csv", index=False)
    for name, df in rejected.items():
        path = REJECTED_DIR / f"{name}_rejected.csv"
        if len(df):
            df.to_csv(path, index=False)
        elif path.exists():
            path.unlink()  # nothing rejected this run, remove old file so it isn't misleading

    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    check_df = pd.DataFrame(CHECK_LOG)
    check_df.insert(0, "run_time", run_time)
    check_df["pct_failed"] = (check_df["rows_failed"] / check_df["rows_checked"] * 100).round(2)
    check_df.to_csv(LOG_DIR / "quality_report.csv", index=False)

    summary_df = pd.DataFrame(TABLE_SUMMARY)
    summary_df.insert(0, "run_time", run_time)
    summary_df.to_csv(LOG_DIR / "table_summary.csv", index=False)
    return check_df, summary_df


def main():
    raw = load_raw()
    clean, rejected = validate_all(raw)
    check_df, summary_df = save_outputs(clean, rejected)

    print("\n=== Rows per table ===")
    print(summary_df.drop(columns="run_time").to_string(index=False))
    print("\n=== Checks that caught something ===")
    caught = check_df[check_df["rows_failed"] > 0]
    print(caught[["table_name", "check_name", "severity", "rows_failed"]].to_string(index=False)
          if len(caught) else "None - all data passed.")
    return clean


if __name__ == "__main__":
    main()
