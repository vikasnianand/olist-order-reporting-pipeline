
![Python](https://img.shields.io/badge/Python-E07A9E?style=for-the-badge&logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-5FA893?style=for-the-badge&logo=pandas&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-7B82C5?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-9BBF65?style=for-the-badge&logo=sqlite&logoColor=white)
![Tableau](https://img.shields.io/badge/Tableau-E0636F?style=for-the-badge&logo=tableau&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-A17E7E?style=for-the-badge&logo=github&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-A17E7E?style=for-the-badge&logo=github&logoColor=white)


# Olist Order Reporting Pipeline

![Dashboard Screenshot](docs/images/Dashboard.png)

An automated data pipeline and warehouse that turns raw e-commerce order data
into a dashboard an operations manager can trust — with every row checked
before it reaches them.

## The business problem

An operations manager at an online marketplace needs weekly numbers on
orders, deliveries, and seller performance. Today that means combining
several files by hand, which is slow and occasionally wrong — a duplicate
order or an impossible delivery date can slip into a report and nobody
notices until a decision is already made on it.

**This project builds the system that removes that risk:** raw data goes in,
gets validated and cleaned automatically, lands in a proper warehouse, and
feeds a dashboard that also shows how trustworthy each week's data was.

- **User:** an operations manager reviewing weekly performance.
- **Decision it supports:** which sellers or regions need attention this
  week, and whether this week's numbers can be trusted.
- **Success measure:** manual reporting hours removed, and the number (and
  %) of bad rows caught before they reach a report.

## What it found (on the sample data used to build and test this)

Out of 2,012 orders, **35 (1.7%) failed a data quality check** — duplicates,
orders pointing at customers that don't exist, and deliveries dated before
the purchase. Those rows were removed and logged with a reason, rather than
silently entering a report. See `logs/quality_report.csv` after a run.

Among delivered orders, **6 out of 60 sellers** show handover times of 7–8
days versus roughly 2–3 days for everyone else, and their orders are late
45–62% of the time (versus about 16% company-wide). That's the kind of
finding an operations manager could act on directly — see
[project 3](#) once it's built on this same warehouse.

## How it works

See `docs/pipeline_diagram.md` for the full flow. In short:

1. **Raw zone** (`data/raw/`) — the untouched CSVs, exactly as received.
2. **Validate** (`pipeline/validate.py`) — about 25 rules across 7 tables
   (missing IDs, duplicates, impossible dates, negative prices, orphaned
   records...). Rows that fail an "error" rule are removed and logged with
   why; rows that fail a "warning" rule are kept but counted.
3. **Transform** (`pipeline/transform.py`) — builds a star schema: dimension
   tables (customer, seller, product, date) and fact tables (orders, order
   items), with business columns calculated once (delivery days, late flag,
   handover days) so every report uses the same definition.
4. **Load** (`pipeline/load.py`) — applies `sql/schema.sql` and loads every
   table plus the quality logs into the warehouse.
5. **Dashboard** — Tableau connects to the warehouse's views
   (`vw_kpi_monthly`, `vw_seller_performance`, `vw_category_performance`,
   `vw_state_performance`, `vw_data_quality`) and needs no further
   transformation.

## Data

Built for the [Olist Brazilian E-Commerce
dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (not
included here — download it and unzip into `data/raw/`, matching the
filenames in `pipeline/config.py`).

To test the pipeline right now without downloading anything, generate a
small fake dataset in the same shape, with errors planted on purpose so you
can watch validation catch them:

```bash
pip install -r requirements.txt
python pipeline/generate_sample_data.py
```

## Running it

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Get data into data/raw/ (real Olist files, or the sample generator above)

# 3. Set where the warehouse lives (optional — defaults to a local SQLite file)
#    MySQL example:
#    export DB_URL="mysql+pymysql://root:yourpassword@localhost:3306/olist_dw"

# 4. Run the pipeline
python pipeline/load.py       # runs validate.py, builds schema, loads everything
```

Check it worked:

```bash
python -c "import sqlite3,pandas as pd; c=sqlite3.connect('olist_warehouse.db'); \
print(pd.read_sql('SELECT * FROM vw_kpi_monthly LIMIT 5', c))"
```

Then connect Tableau to the same database and build visuals
straight from the `vw_*` views.

## Design decisions (so I can defend them)

- **Errors vs warnings:** a row is only removed when the problem makes it
  unsafe to report on (an impossible date, a missing foreign key). A missing
  product category is kept and labelled "unknown" instead of dropped,
  because losing real sales data over one soft field is worse than labelling
  it.
- **`is_late` is `NULL`, not `0`, until an order is actually delivered.**
  Treating "not yet delivered" as "on time" would understate the late rate.
- **Two fact tables, not one:** `fact_orders` (one row per order) answers
  "how are we doing overall", `fact_order_items` (one row per product line,
  carries the seller) answers "which seller or product is the problem."
  Keeping them separate avoids double-counting revenue on multi-item orders.
- **SQLite by default, MySQL by one environment variable:** the same
  `schema.sql` and pipeline code run on both, so this can be tested in
  seconds and still deployed to a real warehouse.

## Limits and what I'd test next

- The sample data's errors are synthetic; real Olist data may have problems
  these specific rules don't catch (e.g. category translations with no
  English equivalent). I'd re-run the quality report on the real files and
  look at the actual `rejected/*.csv` outputs before trusting any number.
- "Late" is defined against Olist's own estimated delivery date. A real
  company might define it differently (e.g. against an SLA by region), and
  that definition should be confirmed with the business user, not assumed.
- With the company's real data, I'd add alerting (email or Slack) when a
  run's rejection rate crosses a threshold, instead of only logging it.

## Repo structure

```
pipeline/     validate.py, transform.py, load.py, config.py, generate_sample_data.py
sql/          schema.sql — the star schema and Power BI views
data/         raw/ clean/ rejected/ (gitignored — see .gitignore)
logs/         quality_report.csv, table_summary.csv (written on each run)
docs/         pipeline_diagram.md
```
