"""
transform.py - STEP 2 of the pipeline: turn clean tables into a star schema.

Star schema in plain words:
  - FACT tables hold the events and numbers (an order happened, it cost X, it took Y days)
  - DIMENSION tables describe the "who / what / when / where" (customer, seller, product, date)
A dashboard joins facts to dimensions, which makes reports fast and simple.

We also calculate business columns here (delivery days, is_late...) ONCE, so
every report uses the same definition instead of each person inventing their own.

Usage:  python pipeline/transform.py   (needs validate.py to have run first)
"""
import numpy as np
import pandas as pd

from config import CLEAN_DIR


def read_clean(name):
    return pd.read_csv(CLEAN_DIR / f"{name}_clean.csv")


def days_between(later, earlier):
    """Whole + fractional days between two timestamps. Blank if either is blank."""
    return (later - earlier).dt.total_seconds() / 86400


def build_dim_date(start, end):
    days = pd.date_range(start, end, freq="D")
    d = pd.DataFrame({"full_date": days})
    d["date_key"] = d["full_date"].dt.strftime("%Y%m%d").astype(int)
    d["year"] = d["full_date"].dt.year
    d["quarter"] = d["full_date"].dt.quarter
    d["month"] = d["full_date"].dt.month
    d["month_name"] = d["full_date"].dt.strftime("%B")
    d["year_month"] = d["full_date"].dt.strftime("%Y-%m")   # handy for sorting charts
    d["week_of_year"] = d["full_date"].dt.isocalendar().week.astype(int)
    d["day_of_week"] = d["full_date"].dt.dayofweek + 1       # 1 = Monday
    d["day_name"] = d["full_date"].dt.strftime("%A")
    d["is_weekend"] = (d["day_of_week"] >= 6).astype(int)
    return d[["date_key", "full_date", "year", "quarter", "month", "month_name",
              "year_month", "week_of_year", "day_of_week", "day_name", "is_weekend"]]


def transform():
    customers = read_clean("customers")
    sellers = read_clean("sellers")
    products = read_clean("products")
    translation = read_clean("category_translation")
    orders = read_clean("orders")
    items = read_clean("items")
    payments = read_clean("payments")
    reviews = read_clean("reviews")

    # ---------- dimensions ----------
    dim_customer = customers.rename(columns={
        "customer_zip_code_prefix": "zip_prefix", "customer_city": "city", "customer_state": "state"})[
        ["customer_id", "customer_unique_id", "city", "state", "zip_prefix"]]

    dim_seller = sellers.rename(columns={
        "seller_zip_code_prefix": "zip_prefix", "seller_city": "city", "seller_state": "state"})[
        ["seller_id", "city", "state", "zip_prefix"]]

    dim_product = products.merge(translation, on="product_category_name", how="left")
    dim_product["category_en"] = dim_product["product_category_name_english"].fillna("unknown")
    dim_product = dim_product.rename(columns={
        "product_category_name": "category_pt", "product_weight_g": "weight_g",
        "product_length_cm": "length_cm", "product_height_cm": "height_cm", "product_width_cm": "width_cm"})
    dim_product = dim_product[["product_id", "category_pt", "category_en",
                               "weight_g", "length_cm", "height_cm", "width_cm"]]

    # ---------- order-level numbers ----------
    for col in ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
                "order_delivered_customer_date", "order_estimated_delivery_date"]:
        orders[col] = pd.to_datetime(orders[col], errors="coerce")

    o = orders
    o["approval_hours"] = days_between(o["order_approved_at"], o["order_purchase_timestamp"]) * 24
    o["handover_days"] = days_between(o["order_delivered_carrier_date"], o["order_approved_at"])   # seller -> carrier
    o["transit_days"] = days_between(o["order_delivered_customer_date"], o["order_delivered_carrier_date"])  # carrier -> customer
    o["total_delivery_days"] = days_between(o["order_delivered_customer_date"], o["order_purchase_timestamp"])
    o["promised_days"] = days_between(o["order_estimated_delivery_date"], o["order_purchase_timestamp"])
    o["days_vs_promise"] = days_between(o["order_delivered_customer_date"], o["order_estimated_delivery_date"])  # + means late
    # is_late: only meaningful once delivered. Not delivered yet -> blank, NOT 0.
    o["is_late"] = np.where(o["order_delivered_customer_date"].isna(), np.nan,
                            (o["days_vs_promise"] > 0).astype(float))

    item_totals = items.groupby("order_id").agg(
        item_count=("order_item_id", "count"),
        items_value=("price", "sum"), freight_value=("freight_value", "sum")).reset_index()

    pay_totals = payments.groupby("order_id").agg(
        payment_value=("payment_value", "sum")).reset_index()
    main_pay = (payments.sort_values(["order_id", "payment_sequential"])
                .drop_duplicates("order_id")[["order_id", "payment_type"]])

    review_scores = reviews.groupby("order_id").agg(review_score=("review_score", "mean")).reset_index()

    fact_orders = (o.merge(item_totals, on="order_id", how="left")
                   .merge(pay_totals, on="order_id", how="left")
                   .merge(main_pay, on="order_id", how="left")
                   .merge(review_scores, on="order_id", how="left"))
    fact_orders["purchase_date_key"] = fact_orders["order_purchase_timestamp"].dt.strftime("%Y%m%d").astype(int)
    fact_orders = fact_orders.rename(columns={
        "order_status": "status", "order_purchase_timestamp": "purchased_at", "order_approved_at": "approved_at",
        "order_delivered_carrier_date": "handed_to_carrier_at", "order_delivered_customer_date": "delivered_at",
        "order_estimated_delivery_date": "promised_at", "payment_type": "main_payment_type"})
    fact_orders = fact_orders[[
        "order_id", "customer_id", "purchase_date_key", "status", "purchased_at", "approved_at",
        "handed_to_carrier_at", "delivered_at", "promised_at", "approval_hours", "handover_days",
        "transit_days", "total_delivery_days", "promised_days", "days_vs_promise", "is_late",
        "item_count", "items_value", "freight_value", "payment_value", "main_payment_type", "review_score"]]
    for c in ["approval_hours", "handover_days", "transit_days", "total_delivery_days",
              "promised_days", "days_vs_promise", "review_score"]:
        fact_orders[c] = fact_orders[c].round(2)

    # ---------- order item fact (one row per product line, has the SELLER) ----------
    # Project 3 needs this: delays are traced back to sellers, so each line carries its order's timing.
    order_timing = fact_orders[["order_id", "purchase_date_key", "status", "handover_days",
                                "transit_days", "total_delivery_days", "is_late", "review_score"]]
    fact_order_items = items.merge(order_timing, on="order_id", how="left").rename(columns={
        "price": "item_price", "freight_value": "item_freight"})
    fact_order_items = fact_order_items[[
        "order_id", "order_item_id", "product_id", "seller_id", "purchase_date_key", "status",
        "item_price", "item_freight", "handover_days", "transit_days", "total_delivery_days",
        "is_late", "review_score"]]

    # ---------- date dimension covers every purchase date ----------
    dim_date = build_dim_date(fact_orders["purchased_at"].min().normalize(),
                              fact_orders["purchased_at"].max().normalize())

    return {
        "dim_date": dim_date, "dim_customer": dim_customer, "dim_seller": dim_seller,
        "dim_product": dim_product, "fact_orders": fact_orders, "fact_order_items": fact_order_items,
    }


if __name__ == "__main__":
    tables = transform()
    for name, df in tables.items():
        print(f"{name:18s} {len(df):>6,} rows  {df.shape[1]} columns")
    fo = tables["fact_orders"]
    print(f"\nShare of delivered orders that were late: {fo['is_late'].mean():.1%}")
