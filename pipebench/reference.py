"""Reference remediations written by the benchmark author. They exist only to
prove that every 'fix' incident is solvable and that the scorer accepts a
correct answer; they are never shown to agents."""

SILVER = """CREATE OR REPLACE TABLE silver_transactions AS
SELECT CAST(txn_id AS BIGINT) AS txn_id, {cust} AS customer_id, {merch} AS merchant_id,
       {amt} AS amount, {ts} AS txn_ts, CAST({ts} AS DATE) AS txn_date
FROM {src} WHERE {where}"""


def silver(cust="customer_id", merch="CAST(merchant_id AS INTEGER)", amt="CAST(amount AS DECIMAL(12,2))",
           ts="CAST(txn_ts AS TIMESTAMP)", src="raw_transactions", where="status = 'POSTED'"):
    return SILVER.format(cust=cust, merch=merch, amt=amt, ts=ts, src=src, where=where)


DEDUP_LATEST = ("CREATE OR REPLACE VIEW tx_latest AS SELECT * FROM raw_transactions "
                "QUALIFY row_number() OVER (PARTITION BY txn_id ORDER BY ingest_ts DESC) = 1")


def fix(**kw):
    return {"decision": "fix", "confidence": 0.9, **kw}


REFERENCE = {
    "F1a": fix(step_overrides={"silver_transactions": silver(amt="CAST(txn_amount AS DECIMAL(12,2))")}),
    "F1b": fix(step_overrides={"silver_transactions": silver(
        amt="CAST(replace(replace(amount, '$', ''), ',', '') AS DECIMAL(12,2))")}),
    "F1c": fix(step_overrides={"silver_transactions": silver(
        ts="CASE WHEN regexp_matches(txn_ts, '^[0-9]+$') THEN make_timestamp(CAST(txn_ts AS BIGINT) * 1000) "
           "ELSE CAST(txn_ts AS TIMESTAMP) END")}),
    "F1d": fix(step_overrides={"silver_transactions": silver(where="upper(status) = 'POSTED'")}),
    "F2a": fix(pre_sql=[DEDUP_LATEST], step_overrides={"silver_transactions": silver(src="tx_latest")}),
    "F2b": fix(pre_sql=[DEDUP_LATEST], step_overrides={"silver_transactions": silver(src="tx_latest")}),
    "F2c": fix(pre_sql=[DEDUP_LATEST], step_overrides={"silver_transactions": silver(src="tx_latest")}),
    "F2d": fix(step_overrides={"silver_merchants": "CREATE OR REPLACE TABLE silver_merchants AS "
                               "SELECT DISTINCT CAST(merchant_id AS INTEGER) AS merchant_id, mcc FROM raw_merchants"}),
    "F3a": fix(step_overrides={"silver_transactions": silver(
        ts="CASE WHEN source_tz = 'UTC' THEN CAST(txn_ts AS TIMESTAMP) - INTERVAL 6 HOUR ELSE CAST(txn_ts AS TIMESTAMP) END")}),
    "F3b": fix(step_overrides={"silver_transactions": silver()}),
    "F3c": fix(step_overrides={"silver_transactions": silver()}),
    "F3d": fix(step_overrides={"silver_transactions": silver(
        ts="coalesce(TRY_CAST(txn_ts AS TIMESTAMP), strptime(txn_ts, '%d/%m/%Y %H:%M:%S'))")}),
    "F4a": fix(step_overrides={"silver_transactions": silver(
        cust="'C' || lpad(substr(customer_id, 2), 5, '0')")}),
    "F4b": fix(step_overrides={"silver_transactions": silver(cust="upper(customer_id)")}),
    "F4c": fix(step_overrides={"silver_customers": "CREATE OR REPLACE TABLE silver_customers AS "
                               "SELECT customer_id, upper(region) AS region FROM raw_customers WHERE is_current"}),
    "F4d": fix(step_overrides={"silver_customers": "CREATE OR REPLACE TABLE silver_customers AS "
                               "SELECT customer_id, upper(trim(region)) AS region FROM raw_customers"}),
    "F5a": fix(step_overrides={"silver_transactions": silver(
        amt="CAST(CASE WHEN amount_unit = 'USD_CENTS' THEN amount / 100 ELSE amount END AS DECIMAL(12,2))")}),
    "F5b": fix(pre_sql=["CREATE OR REPLACE VIEW tx_usd AS SELECT t.* REPLACE "
                        "(CAST(t.amount * f.rate_to_usd AS DECIMAL(12,2)) AS amount) "
                        "FROM raw_transactions t JOIN raw_fx_rates f USING (currency)"],
               step_overrides={"silver_transactions": silver(src="tx_usd")}),
    "F5c": fix(step_overrides={"silver_transactions": silver(where="status IN ('POSTED', 'SETTLED')")}),
    "F5d": fix(step_overrides={"silver_transactions": silver(
        merch="CAST(regexp_replace(merchant_id, '^M-', '') AS INTEGER)")}),
    "H1": fix(step_overrides={"silver_transactions": silver(
        amt="CAST(replace(replace(amount, '$', ''), ',', '') AS DECIMAL(12,2))", where="upper(status) = 'POSTED'")}),
    "H2": fix(pre_sql=["CREATE OR REPLACE VIEW tx_v AS SELECT * FROM raw_transactions "
                       "QUALIFY row_number() OVER (PARTITION BY txn_id ORDER BY record_version DESC) = 1"],
              step_overrides={"silver_transactions": silver(src="tx_v")}),
    "H3": fix(step_overrides={"silver_transactions": silver(
        ts="CASE WHEN collector = 'v2' THEN CAST(txn_ts AS TIMESTAMP) - INTERVAL 6 HOUR ELSE CAST(txn_ts AS TIMESTAMP) END")}),
    "H4": fix(step_overrides={"silver_customers": "CREATE OR REPLACE TABLE silver_customers AS "
                              "SELECT c.customer_id, upper(coalesce(m.region_name, c.region)) AS region "
                              "FROM raw_customers c LEFT JOIN raw_region_map m ON c.region = m.region_code"}),
    "H5": fix(step_overrides={"silver_transactions": silver(
        where="status = 'POSTED' AND txn_id NOT IN (SELECT orig_txn_id FROM raw_transactions "
              "WHERE status = 'REVERSAL' AND orig_txn_id IS NOT NULL)")}),
    "H8": fix(pre_sql=["CREATE OR REPLACE VIEW tx_l AS SELECT * FROM raw_transactions "
                       "QUALIFY row_number() OVER (PARTITION BY txn_id ORDER BY ingest_ts DESC) = 1"],
              step_overrides={"silver_transactions": silver(src="tx_l",
        ts="CASE WHEN regexp_matches(txn_ts, '^[0-9]+$') THEN make_timestamp(CAST(txn_ts AS BIGINT) * 1000) "
           "ELSE CAST(txn_ts AS TIMESTAMP) END")}),
    "H6": {"decision": "escalate", "confidence": 0.9},
    "H7": {"decision": "escalate", "confidence": 0.9},
    "F6a": {"decision": "escalate", "confidence": 0.9},
    "F6b": {"decision": "escalate", "confidence": 0.9},
    "F6c": {"decision": "escalate", "confidence": 0.9},
    "F6d": {"decision": "escalate", "confidence": 0.9},
}
