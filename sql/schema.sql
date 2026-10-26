-- schema.sql : the warehouse (star schema) and the views Power BI reads from.
-- Written to run on MySQL AND SQLite, so you can test locally and deploy to MySQL.
-- Run order matters: views first (they depend on tables), then tables, children before parents.
-- The date_key columns are whole numbers like 20170315, easy to join and sort.

DROP VIEW IF EXISTS vw_order_performance;
DROP VIEW IF EXISTS vw_kpi_monthly;
DROP VIEW IF EXISTS vw_category_performance;
DROP VIEW IF EXISTS vw_seller_performance;
DROP VIEW IF EXISTS vw_state_performance;
DROP VIEW IF EXISTS vw_data_quality;

DROP TABLE IF EXISTS dq_check_log;
DROP TABLE IF EXISTS dq_table_summary;
DROP TABLE IF EXISTS fact_order_items;
DROP TABLE IF EXISTS fact_orders;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_seller;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_date;

-- ---------- dimensions: who, what, when, where ----------

CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,
    full_date     DATE NOT NULL,
    year          INTEGER,
    quarter       INTEGER,
    month         INTEGER,
    month_name    VARCHAR(20),
    year_month    VARCHAR(7),
    week_of_year  INTEGER,
    day_of_week   INTEGER,
    day_name      VARCHAR(20),
    is_weekend    INTEGER
);

CREATE TABLE dim_customer (
    customer_id         VARCHAR(50) PRIMARY KEY,
    customer_unique_id  VARCHAR(50),
    city                VARCHAR(100),
    state               VARCHAR(5),
    zip_prefix          INTEGER
);

CREATE TABLE dim_seller (
    seller_id   VARCHAR(50) PRIMARY KEY,
    city        VARCHAR(100),
    state       VARCHAR(5),
    zip_prefix  INTEGER
);

CREATE TABLE dim_product (
    product_id   VARCHAR(50) PRIMARY KEY,
    category_pt  VARCHAR(100),
    category_en  VARCHAR(100),
    weight_g     DECIMAL(10,2),
    length_cm    DECIMAL(10,2),
    height_cm    DECIMAL(10,2),
    width_cm     DECIMAL(10,2)
);

-- ---------- facts: the events and the numbers ----------

-- One row per order. is_late is NULL until the order is delivered (NULL, not 0).
CREATE TABLE fact_orders (
    order_id              VARCHAR(50) PRIMARY KEY,
    customer_id           VARCHAR(50) NOT NULL,
    purchase_date_key     INTEGER NOT NULL,
    status                VARCHAR(20),
    purchased_at          DATETIME,
    approved_at           DATETIME,
    handed_to_carrier_at  DATETIME,
    delivered_at          DATETIME,
    promised_at           DATETIME,
    approval_hours        DECIMAL(10,2),
    handover_days         DECIMAL(10,2),
    transit_days          DECIMAL(10,2),
    total_delivery_days   DECIMAL(10,2),
    promised_days         DECIMAL(10,2),
    days_vs_promise       DECIMAL(10,2),
    is_late               INTEGER,
    item_count            INTEGER,
    items_value           DECIMAL(12,2),
    freight_value         DECIMAL(12,2),
    payment_value         DECIMAL(12,2),
    main_payment_type     VARCHAR(30),
    review_score          DECIMAL(4,2),
    FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id),
    FOREIGN KEY (purchase_date_key) REFERENCES dim_date (date_key)
);

-- One row per product line in an order. Carries the seller, so delays can be traced to sellers.
CREATE TABLE fact_order_items (
    order_id             VARCHAR(50) NOT NULL,
    order_item_id        INTEGER NOT NULL,
    product_id           VARCHAR(50) NOT NULL,
    seller_id            VARCHAR(50) NOT NULL,
    purchase_date_key    INTEGER NOT NULL,
    status               VARCHAR(20),
    item_price           DECIMAL(12,2),
    item_freight         DECIMAL(12,2),
    handover_days        DECIMAL(10,2),
    transit_days         DECIMAL(10,2),
    total_delivery_days  DECIMAL(10,2),
    is_late              INTEGER,
    review_score         DECIMAL(4,2),
    PRIMARY KEY (order_id, order_item_id),
    FOREIGN KEY (order_id) REFERENCES fact_orders (order_id),
    FOREIGN KEY (product_id) REFERENCES dim_product (product_id),
    FOREIGN KEY (seller_id) REFERENCES dim_seller (seller_id)
);

-- ---------- data quality log: what the validation step found, per run ----------

CREATE TABLE dq_check_log (
    run_time      VARCHAR(25),
    table_name    VARCHAR(50),
    check_name    VARCHAR(60),
    severity      VARCHAR(10),
    description   VARCHAR(200),
    rows_checked  INTEGER,
    rows_failed   INTEGER,
    pct_failed    DECIMAL(6,2)
);

CREATE TABLE dq_table_summary (
    run_time       VARCHAR(25),
    table_name     VARCHAR(50),
    rows_in        INTEGER,
    rows_clean     INTEGER,
    rows_rejected  INTEGER
);

-- ---------- views: ready-made tables for Power BI ----------

-- One row per order with the date and customer state attached.
CREATE VIEW vw_order_performance AS
SELECT o.order_id, o.status, o.purchased_at, d.full_date, d.year, d.quarter, d.month, d.year_month,
       c.state AS customer_state, c.city AS customer_city,
       o.items_value, o.freight_value, o.payment_value, o.main_payment_type,
       o.approval_hours, o.handover_days, o.transit_days, o.total_delivery_days,
       o.promised_days, o.days_vs_promise, o.is_late, o.review_score
FROM fact_orders o
JOIN dim_date d ON d.date_key = o.purchase_date_key
JOIN dim_customer c ON c.customer_id = o.customer_id;

-- The manager's weekly/monthly headline numbers.
CREATE VIEW vw_kpi_monthly AS
SELECT d.year_month,
       COUNT(*)                                                       AS orders,
       SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END)        AS delivered_orders,
       SUM(CASE WHEN o.status = 'delivered' THEN o.items_value ELSE 0 END) AS revenue,
       AVG(o.total_delivery_days)                                     AS avg_delivery_days,
       AVG(o.is_late)                                                 AS late_rate,
       AVG(o.review_score)                                            AS avg_review_score
FROM fact_orders o
JOIN dim_date d ON d.date_key = o.purchase_date_key
GROUP BY d.year_month;

CREATE VIEW vw_category_performance AS
SELECT p.category_en,
       COUNT(*)                 AS order_lines,
       SUM(i.item_price)        AS revenue,
       AVG(i.is_late)           AS late_rate,
       AVG(i.review_score)      AS avg_review_score
FROM fact_order_items i
JOIN dim_product p ON p.product_id = i.product_id
WHERE i.status = 'delivered'
GROUP BY p.category_en;

CREATE VIEW vw_seller_performance AS
SELECT s.seller_id, s.state AS seller_state,
       COUNT(*)                 AS order_lines,
       SUM(i.item_price)        AS revenue,
       AVG(i.handover_days)     AS avg_handover_days,
       AVG(i.total_delivery_days) AS avg_delivery_days,
       AVG(i.is_late)           AS late_rate,
       AVG(i.review_score)      AS avg_review_score
FROM fact_order_items i
JOIN dim_seller s ON s.seller_id = i.seller_id
WHERE i.status = 'delivered'
GROUP BY s.seller_id, s.state;

CREATE VIEW vw_state_performance AS
SELECT c.state AS customer_state,
       COUNT(*)                 AS orders,
       SUM(o.items_value)       AS revenue,
       AVG(o.total_delivery_days) AS avg_delivery_days,
       AVG(o.is_late)           AS late_rate,
       AVG(o.review_score)      AS avg_review_score
FROM fact_orders o
JOIN dim_customer c ON c.customer_id = o.customer_id
WHERE o.status = 'delivered'
GROUP BY c.state;

-- Powers the "Data Quality" page on the dashboard.
CREATE VIEW vw_data_quality AS
SELECT run_time, table_name, check_name, severity, description, rows_checked, rows_failed, pct_failed
FROM dq_check_log;
