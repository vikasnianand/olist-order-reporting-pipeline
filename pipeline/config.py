"""
config.py - one place for all the settings.

Why: if a folder name or database changes, you edit it here once instead of
hunting through every script.
"""
import os
from pathlib import Path

# Project root = the folder that contains /pipeline, /data, /sql
ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = ROOT / "data" / "raw"            # untouched files straight from Kaggle (the "raw zone")
CLEAN_DIR = ROOT / "data" / "clean"        # rows that passed all checks
REJECTED_DIR = ROOT / "data" / "rejected"  # rows that failed a check, with the reason
LOG_DIR = ROOT / "logs"
SQL_DIR = ROOT / "sql"

# Which raw files we need. Keys are short names we use in code.
RAW_FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

# Database connection.
#   Local test (no setup needed):  sqlite:///olist_warehouse.db
#   Your MySQL:  mysql+pymysql://USER:PASSWORD@localhost:3306/olist_dw
# Set it in your terminal instead of typing a password into code:
#   Windows PowerShell:  $env:DB_URL = "mysql+pymysql://root:yourpassword@localhost:3306/olist_dw"
DB_URL = os.environ.get("DB_URL", f"sqlite:///{ROOT / 'olist_warehouse.db'}")

# Optional: AWS S3 bucket for the raw zone. Leave empty to skip the S3 step.
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_RAW_PREFIX = "raw/olist/"

# Business rules used by the checks
MIN_VALID_DATE = "2016-01-01"   # Olist orders start in late 2016
MAX_VALID_DATE = "2018-12-31"   # and end in 2018
