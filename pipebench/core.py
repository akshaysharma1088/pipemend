"""Core of the benchmark: synthetic medallion pipeline, monitors, and gold oracle.

Everything runs in an in-memory DuckDB database so the benchmark needs no cloud
resources. Raw (bronze) tables are pandas DataFrames loaded into DuckDB; the
pipeline is an ordered list of SQL steps that build silver and gold tables.
"""
from __future__ import annotations

import collections
import datetime as dt
import re

import duckdb
import numpy as np
import pandas as pd

START = dt.date(2026, 1, 5)
N_DAYS = 14
REGIONS = ["NORTH", "SOUTH", "EAST", "WEST"]
MCCS = ["5411", "5812", "5541", "5999", "4111"]

BASE_PIPELINE = collections.OrderedDict([
    ("silver_transactions", """CREATE OR REPLACE TABLE silver_transactions AS
SELECT CAST(txn_id AS BIGINT) AS txn_id,
       customer_id,
       CAST(merchant_id AS INTEGER) AS merchant_id,
       CAST(amount AS DECIMAL(12,2)) AS amount,
       CAST(txn_ts AS TIMESTAMP) AS txn_ts,
       CAST(CAST(txn_ts AS TIMESTAMP) AS DATE) AS txn_date
FROM raw_transactions
WHERE status = 'POSTED'"""),
    ("silver_customers", """CREATE OR REPLACE TABLE silver_customers AS
SELECT customer_id, upper(region) AS region
FROM raw_customers"""),
    ("silver_merchants", """CREATE OR REPLACE TABLE silver_merchants AS
SELECT CAST(merchant_id AS INTEGER) AS merchant_id, mcc
FROM raw_merchants"""),
    ("gold_merchant_daily", """CREATE OR REPLACE TABLE gold_merchant_daily AS
SELECT txn_date, merchant_id, count(*) AS n_txn, sum(amount) AS total
FROM silver_transactions
GROUP BY txn_date, merchant_id"""),
    ("gold_region_daily", """CREATE OR REPLACE TABLE gold_region_daily AS
SELECT t.txn_date, c.region, count(*) AS n_txn, sum(t.amount) AS total
FROM silver_transactions t JOIN silver_customers c USING (customer_id)
GROUP BY t.txn_date, c.region"""),
    ("gold_mcc_daily", """CREATE OR REPLACE TABLE gold_mcc_daily AS
SELECT t.txn_date, m.mcc, count(*) AS n_txn, sum(t.amount) AS total
FROM silver_transactions t JOIN silver_merchants m USING (merchant_id)
GROUP BY t.txn_date, m.mcc"""),
    ("gold_customer_spend", """CREATE OR REPLACE TABLE gold_customer_spend AS
SELECT customer_id, count(*) AS n_txn, sum(amount) AS total
FROM silver_transactions
GROUP BY customer_id"""),
])
GOLD_TABLES = [k for k in BASE_PIPELINE if k.startswith("gold_")]
# oracle compares silver tables too (fixed column lists) and all gold tables
CHECKED = {
    "silver_transactions": "txn_id, customer_id, merchant_id, amount, txn_ts, txn_date",
    "silver_customers": "customer_id, region",
    "silver_merchants": "merchant_id, mcc",
    **{g: "*" for g in GOLD_TABLES},
}


# ----------------------------------------------------------------- data
def generate_clean(seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n_cust, n_merch = 200, 40
    customers = pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(1, n_cust + 1)],
        "region": rng.choice(REGIONS, n_cust),
        "signup_date": [START - dt.timedelta(days=int(d)) for d in rng.integers(30, 900, n_cust)],
    })
    merchants = pd.DataFrame({
        "merchant_id": np.arange(100, 100 + n_merch, dtype=np.int64),
        "merchant_name": [f"Merchant {i}" for i in range(n_merch)],
        "mcc": rng.choice(MCCS, n_merch),
    })
    rows = []
    txn_id = 900000
    for d in range(N_DAYS):
        day = START + dt.timedelta(days=d)
        n = int(rng.integers(320, 380))
        batch_id = d + 1
        ingest = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(2, 0))
        secs = np.sort(rng.integers(6 * 3600, 23 * 3600, n))
        for s in secs:
            txn_id += 1
            rows.append({
                "txn_id": txn_id,
                "customer_id": customers.customer_id.iloc[int(rng.integers(0, n_cust))],
                "merchant_id": int(merchants.merchant_id.iloc[int(rng.integers(0, n_merch))]),
                "amount": float(round(float(rng.lognormal(3.4, 0.8)), 2)),
                "currency": "USD",
                "txn_ts": dt.datetime.combine(day, dt.time()) + dt.timedelta(seconds=int(s)),
                "status": "POSTED" if rng.random() > 0.05 else "REVERSED",
                "batch_id": batch_id,
                "ingest_ts": ingest,
            })
    tx = pd.DataFrame(rows)
    return {"raw_transactions": tx, "raw_customers": customers, "raw_merchants": merchants}


def copy_raw(raw):
    return {k: v.copy(deep=True) for k, v in raw.items()}


# ----------------------------------------------------------------- execution
def load(raw: dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone = 'UTC'")
    for name, df in raw.items():
        con.register(f"__{name}", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM __{name}")
        con.unregister(f"__{name}")
    return con


def run_pipeline(con, steps) -> str | None:
    """Run steps in order; return None on success or 'step: error' on failure."""
    for name, sql in steps.items():
        try:
            con.execute(sql)
        except Exception as e:  # noqa: BLE001
            msg = str(e).split("\n")[0]
            return f"{name}: {type(e).__name__}: {msg}"
    return None


def gold_snapshot(con) -> dict[str, collections.Counter]:
    snap = {}
    for t, cols in CHECKED.items():
        try:
            df = con.execute(f"SELECT {cols} FROM {t}").fetchdf()
        except Exception as e:  # noqa: BLE001
            snap[t] = collections.Counter({("ERROR", str(e).splitlines()[0]): 1})
            continue
        recs = []
        for row in df.itertuples(index=False):
            vals = []
            for v in row:
                if isinstance(v, (float, np.floating)) or type(v).__name__ == "Decimal":
                    vals.append(round(float(v), 2))
                elif isinstance(v, (pd.Timestamp, dt.datetime)):
                    ts = pd.Timestamp(v)
                    vals.append(ts.date().isoformat() if ts == ts.normalize() and t.startswith("gold_") else ts.isoformat())
                elif isinstance(v, dt.date):
                    vals.append(v.isoformat())
                elif isinstance(v, (np.integer,)):
                    vals.append(int(v))
                else:
                    vals.append(v)
            recs.append(tuple(vals))
        snap[t] = collections.Counter(recs)
    return snap


def snapshots_equal(a, b) -> tuple[bool, list[str]]:
    diffs = []
    for t in CHECKED:
        if a.get(t) != b.get(t):
            missing = sum((a[t] - b[t]).values()) if t in a and t in b else -1
            extra = sum((b[t] - a[t]).values()) if t in a and t in b else -1
            diffs.append(f"{t}: {missing} expected rows missing, {extra} unexpected rows")
    return (not diffs), diffs


def oracle(clean_raw) -> dict:
    con = load(clean_raw)
    err = run_pipeline(con, BASE_PIPELINE)
    assert err is None, err
    return gold_snapshot(con)


# ----------------------------------------------------------------- monitors
def monitors(con) -> list[str]:
    """Production-style data quality checks that use no ground truth.

    They compare the pipeline outputs with the raw inputs and with the history
    of the same pipeline, the way an on-call engineer's alerts would.
    """
    alerts = []
    q = lambda s: con.execute(s).fetchall()  # noqa: E731
    try:
        dup = q("SELECT count(*) FROM (SELECT txn_id FROM silver_transactions GROUP BY txn_id HAVING count(*) > 1)")[0][0]
        if dup:
            alerts.append(f"DUPLICATE_KEYS: {dup} txn_id values appear more than once in silver_transactions")
        per_day = q("SELECT txn_date, count(*) FROM silver_transactions GROUP BY 1 ORDER BY 1")
        counts = [c for _, c in per_day]
        if len(counts) >= 5:
            med = float(np.median(counts))
            for d, c in per_day:
                if c < 0.7 * med or c > 1.3 * med:
                    alerts.append(f"VOLUME_ANOMALY: silver_transactions has {c} rows for {d} (14-day median {med:.0f})")
        nulls = q("""SELECT sum(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END),
                            sum(CASE WHEN merchant_id IS NULL THEN 1 ELSE 0 END),
                            sum(CASE WHEN amount IS NULL THEN 1 ELSE 0 END),
                            sum(CASE WHEN txn_ts IS NULL THEN 1 ELSE 0 END)
                     FROM silver_transactions""")[0]
        for col, n in zip(["customer_id", "merchant_id", "amount", "txn_ts"], nulls):
            if n:
                alerts.append(f"NULL_VALUES: {n} NULL {col} values in silver_transactions")
        n_silver = q("SELECT count(*) FROM silver_transactions")[0][0]
        for g, lab in [("gold_region_daily", "customer"), ("gold_mcc_daily", "merchant")]:
            n_g = q(f"SELECT coalesce(sum(n_txn),0) FROM {g}")[0][0]
            if n_g != n_silver:
                alerts.append(f"RECONCILIATION: {g} counts {n_g} transactions but silver_transactions has {n_silver} "
                              f"(join to {lab} dimension adds or drops rows)")
        dom = q("SELECT DISTINCT region FROM silver_customers")
        bad = sorted(str(r[0]) for r in dom if r[0] not in REGIONS)
        if bad:
            alerts.append(f"DOMAIN_CHECK: unexpected region values in silver_customers: {bad[:5]}")
        means = q("SELECT txn_date, avg(amount) FROM silver_transactions GROUP BY 1 ORDER BY 1")
        if len(means) >= 5:
            vals = np.array([float(m) for _, m in means])
            med = float(np.median(vals))
            for d, m in means:
                if float(m) > 3 * med or float(m) < med / 3:
                    alerts.append(f"AMOUNT_ANOMALY: mean amount {float(m):.2f} on {d} vs median {med:.2f}")
        night = q("""SELECT txn_date, sum(CASE WHEN hour(txn_ts) < 6 THEN 1 ELSE 0 END), count(*)
                     FROM silver_transactions GROUP BY 1 ORDER BY 1""")
        for d, n_night, n in night:
            if n and n_night > 0.02 * n:
                alerts.append(f"TIME_DISTRIBUTION: {n_night} of {n} transactions on {d} are timestamped 00:00-06:00, "
                              "outside merchant opening hours")
        cols = [r[0] for r in q("SELECT column_name FROM information_schema.columns WHERE table_name = 'raw_transactions'")]
        if "currency" in cols:
            nonusd = q("SELECT currency, count(*) FROM raw_transactions WHERE currency <> 'USD' GROUP BY 1")
            for cur, n in nonusd:
                alerts.append(f"CURRENCY_CHECK: {n} raw_transactions rows have currency {cur}; gold totals are reported in USD")
        bad_dates = q("SELECT count(*) FROM silver_transactions WHERE txn_date <> CAST(txn_ts AS DATE)")[0][0]
        if bad_dates:
            alerts.append(f"DATE_CONSISTENCY: {bad_dates} silver_transactions rows have txn_date different from the date of txn_ts")
        # raw-to-silver completeness per delivery batch, matched on txn_id
        comp = q("""SELECT r.batch_id, count(DISTINCT r.txn_id) AS n_raw,
                           count(DISTINCT CASE WHEN s.txn_id IS NOT NULL THEN r.txn_id END) AS n_found
                    FROM raw_transactions r
                    LEFT JOIN silver_transactions s ON TRY_CAST(r.txn_id AS BIGINT) = s.txn_id
                    GROUP BY 1 ORDER BY 1""")
        for b, n_raw, n_found in comp:
            if n_raw and n_found < 0.85 * n_raw:
                alerts.append(f"RAW_TO_SILVER: batch {b} delivered {n_raw} transactions but only {n_found} reached silver_transactions")
    except Exception as e:  # noqa: BLE001
        alerts.append(f"MONITOR_ERROR: {type(e).__name__}: {str(e).splitlines()[0]}")
    return alerts


# ----------------------------------------------------------------- safety
FORBIDDEN = re.compile(r"\b(UPDATE|DELETE|DROP|ALTER|TRUNCATE|INSERT|COPY|ATTACH|EXPORT|IMPORT|INSTALL|LOAD|PRAGMA|SET)\b", re.I)


def unsafe_statement(sql: str) -> str | None:
    """Fixes may only create views or tables; they may not mutate inputs or gold."""
    s = re.sub(r"--.*?$", "", sql, flags=re.M)
    s = re.sub(r"'(?:[^']|'')*'", "''", s)  # ignore string literals
    m = FORBIDDEN.search(s)
    if m:
        return f"forbidden keyword {m.group(1).upper()}"
    if re.search(r"CREATE\s+(OR\s+REPLACE\s+)?(TABLE|VIEW)\s+(raw_|gold_)", s, re.I):
        return "creates or replaces a raw_ or gold_ object"
    if "read_" in s.lower() or "http" in s.lower():
        return "reads external files"
    return None
