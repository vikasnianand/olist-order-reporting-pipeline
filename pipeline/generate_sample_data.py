"""
generate_sample_data.py - makes a SMALL FAKE dataset shaped exactly like Olist.

Why this exists: so you (and anyone cloning your repo) can test the whole
pipeline in seconds without downloading 100k real orders. It also plants some
deliberate errors (duplicates, impossible dates, negative prices...) so you can
SEE the validation step catching them.

When you have the real Olist files, put them in data/raw/ and skip this script.
Usage:  python pipeline/generate_sample_data.py
"""
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from config import RAW_DIR, RAW_FILES

random.seed(42)
np.random.seed(42)

N_CUSTOMERS = 1500
N_SELLERS = 60
N_PRODUCTS = 300
N_ORDERS = 2000

STATES = ["SP", "RJ", "MG", "RS", "PR", "BA", "SC", "DF"]
CITIES = {"SP": "sao paulo", "RJ": "rio de janeiro", "MG": "belo horizonte", "RS": "porto alegre",
          "PR": "curitiba", "BA": "salvador", "SC": "florianopolis", "DF": "brasilia"}
CATEGORIES = {
    "cama_mesa_banho": "bed_bath_table", "beleza_saude": "health_beauty",
    "esporte_lazer": "sports_leisure", "informatica_acessorios": "computers_accessories",
    "moveis_decoracao": "furniture_decor", "utilidades_domesticas": "housewares",
    "brinquedos": "toys", "relogios_presentes": "watches_gifts",
}


def make_id(prefix, n):
    return f"{prefix}{n:06d}"


def fmt(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(ts) else ""


# ---------- customers ----------
customers = pd.DataFrame({
    "customer_id": [make_id("c", i) for i in range(N_CUSTOMERS)],
    "customer_unique_id": [make_id("u", int(i * 0.9)) for i in range(N_CUSTOMERS)],  # some people order more than once
    "customer_zip_code_prefix": np.random.randint(1000, 99999, N_CUSTOMERS),
})
customers["customer_state"] = np.random.choice(STATES, N_CUSTOMERS, p=[.4, .15, .12, .08, .08, .07, .05, .05])
customers["customer_city"] = customers["customer_state"].map(CITIES)

# ---------- sellers ----------
sellers = pd.DataFrame({
    "seller_id": [make_id("s", i) for i in range(N_SELLERS)],
    "seller_zip_code_prefix": np.random.randint(1000, 99999, N_SELLERS),
})
sellers["seller_state"] = np.random.choice(STATES, N_SELLERS, p=[.5, .12, .1, .06, .08, .05, .05, .04])
sellers["seller_city"] = sellers["seller_state"].map(CITIES)
# A few "problem sellers" who ship slowly - this is the story project 3 will find
slow_sellers = set(random.sample(list(sellers["seller_id"]), 6))

# ---------- products ----------
products = pd.DataFrame({
    "product_id": [make_id("p", i) for i in range(N_PRODUCTS)],
    "product_category_name": np.random.choice(list(CATEGORIES), N_PRODUCTS),
    "product_name_lenght": np.random.randint(20, 60, N_PRODUCTS),        # (sic) Olist's real column has this typo
    "product_description_lenght": np.random.randint(100, 2000, N_PRODUCTS),
    "product_photos_qty": np.random.randint(1, 8, N_PRODUCTS),
    "product_weight_g": np.random.randint(100, 8000, N_PRODUCTS),
    "product_length_cm": np.random.randint(10, 80, N_PRODUCTS),
    "product_height_cm": np.random.randint(5, 50, N_PRODUCTS),
    "product_width_cm": np.random.randint(10, 60, N_PRODUCTS),
})
# real Olist has some products with missing category - mimic that
products.loc[products.sample(8, random_state=1).index, "product_category_name"] = np.nan

category_translation = pd.DataFrame({
    "product_category_name": list(CATEGORIES.keys()),
    "product_category_name_english": list(CATEGORIES.values()),
})

# ---------- orders, items, payments, reviews ----------
start = datetime(2017, 1, 1)
orders, items, payments, reviews = [], [], [], []

for i in range(N_ORDERS):
    order_id = make_id("o", i)
    cust = random.choice(customers["customer_id"].tolist())
    purchase = start + timedelta(days=random.randint(0, 600), hours=random.randint(0, 23), minutes=random.randint(0, 59))
    approved = purchase + timedelta(hours=random.choice([0, 1, 2, 6, 12, 24]))

    # pick 1-3 items, each with a seller
    n_items = random.choices([1, 2, 3], weights=[.8, .15, .05])[0]
    order_sellers = []
    for k in range(n_items):
        seller = random.choice(sellers["seller_id"].tolist())
        order_sellers.append(seller)
        price = round(random.uniform(15, 400), 2)
        items.append({
            "order_id": order_id, "order_item_id": k + 1,
            "product_id": random.choice(products["product_id"].tolist()),
            "seller_id": seller,
            "shipping_limit_date": fmt(approved + timedelta(days=3)),
            "price": price, "freight_value": round(random.uniform(5, 45), 2),
        })

    # handover to carrier: slow sellers are the bottleneck
    slow = any(s in slow_sellers for s in order_sellers)
    carrier = approved + timedelta(days=random.randint(5, 10) if slow else random.randint(1, 3))
    transit_days = random.randint(4, 14)
    delivered = carrier + timedelta(days=transit_days)
    estimated = purchase + timedelta(days=random.randint(12, 22))

    status = random.choices(["delivered", "shipped", "canceled", "processing"], weights=[.93, .03, .02, .02])[0]
    if status in ("canceled", "processing"):
        carrier = delivered = pd.NaT
    elif status == "shipped":
        delivered = pd.NaT

    orders.append({
        "order_id": order_id, "customer_id": cust, "order_status": status,
        "order_purchase_timestamp": fmt(purchase), "order_approved_at": fmt(approved),
        "order_delivered_carrier_date": fmt(carrier), "order_delivered_customer_date": fmt(delivered),
        "order_estimated_delivery_date": fmt(estimated),
    })

    total = sum(it["price"] + it["freight_value"] for it in items if it["order_id"] == order_id)
    payments.append({
        "order_id": order_id, "payment_sequential": 1,
        "payment_type": random.choices(["credit_card", "boleto", "voucher", "debit_card"], weights=[.74, .19, .05, .02])[0],
        "payment_installments": random.choice([1, 1, 1, 2, 3, 5, 10]),
        "payment_value": round(total, 2),
    })

    # reviews: late deliveries get worse scores (this is what makes project 3 interesting)
    if status == "delivered":
        is_late = pd.notna(delivered) and delivered > estimated
        score = random.choices([1, 2, 3, 4, 5], weights=[.45, .2, .15, .1, .1] if is_late else [.03, .03, .08, .26, .6])[0]
        reviews.append({
            "review_id": f"r{i:06d}", "order_id": order_id, "review_score": score,
            "review_comment_title": "", "review_comment_message": "",
            "review_creation_date": fmt(delivered + timedelta(days=1)),
            "review_answer_timestamp": fmt(delivered + timedelta(days=3)),
        })

orders = pd.DataFrame(orders)
items = pd.DataFrame(items)
payments = pd.DataFrame(payments)
reviews = pd.DataFrame(reviews)

# ---------- plant deliberate errors so validation has something to catch ----------
# 1. duplicate orders (same row twice)
orders = pd.concat([orders, orders.sample(12, random_state=2)], ignore_index=True)
# 2. delivered BEFORE purchased (impossible)
bad = orders[orders["order_status"] == "delivered"].sample(10, random_state=3).index
orders.loc[bad, "order_delivered_customer_date"] = "2016-06-01 10:00:00"
# 3. orders pointing to a customer that doesn't exist
orders.loc[orders.sample(6, random_state=4).index, "customer_id"] = "c_missing"
# 4. delivered orders with no delivery date
miss = orders[orders["order_status"] == "delivered"].sample(8, random_state=5).index
orders.loc[miss, "order_delivered_customer_date"] = ""
# 5. negative prices and zero-price items
items.loc[items.sample(7, random_state=6).index, "price"] = -10.0
items.loc[items.sample(4, random_state=7).index, "price"] = 0.0
# 6. review scores outside 1-5
reviews.loc[reviews.sample(5, random_state=8).index, "review_score"] = 9
# 7. items pointing to a product that doesn't exist
items.loc[items.sample(5, random_state=9).index, "product_id"] = "p_missing"

# ---------- save ----------
RAW_DIR.mkdir(parents=True, exist_ok=True)
tables = {
    "customers": customers, "orders": orders, "items": items, "payments": payments,
    "reviews": reviews, "products": products, "sellers": sellers,
    "category_translation": category_translation,
}
for key, df in tables.items():
    df.to_csv(RAW_DIR / RAW_FILES[key], index=False)
    print(f"wrote {RAW_FILES[key]:45s} {len(df):>6,} rows")
print("\nSample data ready in data/raw/ (with deliberate errors planted).")
