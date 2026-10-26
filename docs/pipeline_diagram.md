```
   data/raw/*.csv          validate.py              data/clean/*.csv
  (Olist export,     ──▶   runs ~25 rules    ──▶    (rows that passed)
   untouched)               per table                        │
                                 │                            │
                                 ▼                            ▼
                         data/rejected/*.csv          transform.py
                        (bad rows + reason,         builds dimensions
                         logs/quality_report.csv)    (customer, seller,
                                 │                     product, date)
                                 │                   and facts (orders,
                                 │                     order items)
                                 │                            │
                                 └──────────┬─────────────────┘
                                            ▼
                                       load.py
                              applies sql/schema.sql, then
                              loads every table + the logs
                                            │
                                            ▼
                               MySQL / SQLite warehouse
                              (star schema: dim_* + fact_*
                               + dq_check_log, dq_table_summary)
                                            │
                                            ▼
                                   Power BI dashboard
                           (vw_kpi_monthly, vw_seller_performance,
                            vw_category_performance, vw_state_performance,
                            vw_order_performance, vw_data_quality)
```
Paste this into draw.io (or redraw it there) for the README — a drawn box-and-arrow
version reads better than ASCII art once it's in the actual repo.
