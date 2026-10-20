"""24 incidents in six families. Each builder returns the clean raw data (ground
truth), the faulty raw data the pipeline actually receives, the pipeline as
currently deployed, and source change notes visible to the agent.

expected = "fix": a correct fix exists and the oracle is the base pipeline on clean data.
expected = "escalate": no safe, uniquely determined fix exists from the evidence.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import numpy as np
import pandas as pd

from .core import BASE_PIPELINE, copy_raw, generate_clean

GENERIC_NOTES = [
    "2026-01-08 platform: Airflow upgraded to 2.10; no DAG changes.",
    "2026-01-12 analytics: dashboard filters for region pages updated.",
]


@dataclasses.dataclass
class Incident:
    iid: str
    family: str
    title: str          # internal only, never shown to agents
    expected: str       # "fix" or "escalate"
    builder: object
    complaint: str = ""  # optional user report shown with the symptom
    split: str = "core"


def _rng(seed, salt):
    return np.random.default_rng(seed * 1000 + salt)


def _batch(rng):
    return int(rng.choice([12, 13, 14]))


def _base(seed):
    clean = generate_clean(seed)
    return clean, copy_raw(clean), dict(BASE_PIPELINE), list(GENERIC_NOTES)


def _iso(ts):
    return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ F1 schema drift
def f1a(seed):
    clean, raw, pipe, notes = _base(seed)
    raw["raw_transactions"] = raw["raw_transactions"].rename(columns={"amount": "txn_amount"})
    return clean, raw, pipe, notes


def f1b(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 12))
    tx = raw["raw_transactions"]
    m = tx.batch_id == b
    tx["amount"] = [f"${a:,.2f}" if mm else f"{a:.2f}" for a, mm in zip(tx.amount, m)]
    return clean, raw, pipe, notes


def f1c(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 13))
    tx = raw["raw_transactions"]
    m = tx.batch_id == b
    tx["txn_ts"] = [str(int(pd.Timestamp(t).value // 1_000_000)) if mm else _iso(t) for t, mm in zip(tx.txn_ts, m)]
    return clean, raw, pipe, notes


def f1d(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 14))
    tx = raw["raw_transactions"]
    m = tx.batch_id == b
    tx.loc[m, "status"] = tx.loc[m, "status"].str.lower()
    return clean, raw, pipe, notes


# ------------------------------------------------------------------ F2 duplicates
def f2a(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 21))
    tx = raw["raw_transactions"]
    rep = tx[tx.batch_id == b].copy()
    rep["ingest_ts"] = rep["ingest_ts"] + pd.Timedelta(hours=3)
    raw["raw_transactions"] = pd.concat([tx, rep], ignore_index=True)
    return clean, raw, pipe, notes


def f2b(seed):
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 22)
    tx = raw["raw_transactions"]
    dup = tx.sample(frac=0.03, random_state=int(rng.integers(0, 10**6)))
    raw["raw_transactions"] = pd.concat([tx, dup], ignore_index=True).sort_values(["batch_id", "txn_ts"]).reset_index(drop=True)
    return clean, raw, pipe, notes


def f2c(seed):
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 23)
    b = _batch(rng)
    ctx = clean["raw_transactions"]
    idx = ctx[ctx.batch_id == b].sample(frac=0.06, random_state=int(rng.integers(0, 10**6))).index
    tx = raw["raw_transactions"]
    corr = tx.loc[idx].copy()
    new_amt = [round(a * float(rng.uniform(0.5, 1.5)), 2) for a in corr.amount]
    corr["amount"] = new_amt
    corr["ingest_ts"] = corr["ingest_ts"] + pd.Timedelta(hours=20)
    ctx.loc[idx, "amount"] = new_amt  # ground truth is the corrected value
    raw["raw_transactions"] = pd.concat([tx, corr], ignore_index=True)
    return clean, raw, pipe, notes


def f2d(seed):
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 24)
    mr = raw["raw_merchants"]
    dup = mr.sample(n=6, random_state=int(rng.integers(0, 10**6)))
    raw["raw_merchants"] = pd.concat([mr, dup], ignore_index=True)
    return clean, raw, pipe, notes


# ------------------------------------------------------------------ F3 time and lateness
def f3a(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 31))
    tx = raw["raw_transactions"]
    tx["source_tz"] = "America/Chicago"
    m = tx.batch_id == b
    tx.loc[m, "txn_ts"] = tx.loc[m, "txn_ts"] + pd.Timedelta(hours=6)
    tx.loc[m, "source_tz"] = "UTC"
    return clean, raw, pipe, notes


def f3b(seed):
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 32)
    ctx = clean["raw_transactions"]
    late_idx = ctx[(ctx.batch_id <= 12) & (rng.random(len(ctx)) < 0.20)].index
    for data in (clean, raw):  # late arrivals are real data in both
        tx = data["raw_transactions"]
        tx.loc[late_idx, "ingest_ts"] = tx.loc[late_idx, "ingest_ts"] + pd.Timedelta(days=2)
        tx.loc[late_idx, "batch_id"] = tx.loc[late_idx, "batch_id"] + 2
    pipe["silver_transactions"] = BASE_PIPELINE["silver_transactions"].replace(
        "WHERE status = 'POSTED'",
        "WHERE status = 'POSTED'\n  AND ingest_ts - CAST(txn_ts AS TIMESTAMP) <= INTERVAL 26 HOUR")
    notes.append("2026-01-17 data-eng: silver_transactions now filters stale events (ticket DE-412).")
    return clean, raw, pipe, notes


def f3c(seed):
    clean, raw, pipe, notes = _base(seed)
    pipe["silver_transactions"] = BASE_PIPELINE["silver_transactions"].replace(
        "CAST(CAST(txn_ts AS TIMESTAMP) AS DATE) AS txn_date", "CAST(ingest_ts AS DATE) AS txn_date")
    notes.append("2026-01-16 data-eng: refactored date derivation in silver_transactions (ticket DE-398).")
    return clean, raw, pipe, notes


def f3d(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 34))
    tx = raw["raw_transactions"]
    m = tx.batch_id == b
    tx["txn_ts"] = [pd.Timestamp(t).strftime("%d/%m/%Y %H:%M:%S") if mm else _iso(t) for t, mm in zip(tx.txn_ts, m)]
    return clean, raw, pipe, notes


# ------------------------------------------------------------------ F4 keys and joins
def f4a(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 41))
    tx = raw["raw_transactions"]
    m = tx.batch_id == b
    tx.loc[m, "customer_id"] = ["C" + str(int(c[1:])) for c in tx.loc[m, "customer_id"]]
    return clean, raw, pipe, notes


def f4b(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 42))
    tx = raw["raw_transactions"]
    m = tx.batch_id == b
    tx.loc[m, "customer_id"] = tx.loc[m, "customer_id"].str.lower()
    return clean, raw, pipe, notes


def f4c(seed):
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 43)
    cu = raw["raw_customers"]
    cu["is_current"] = True
    cu["valid_from"] = pd.Timestamp("2025-01-01")
    hist = cu.sample(n=30, random_state=int(rng.integers(0, 10**6))).copy()
    hist["region"] = [rng.choice([r for r in ["NORTH", "SOUTH", "EAST", "WEST"] if r != x]) for x in hist.region]
    hist["is_current"] = False
    hist["valid_from"] = pd.Timestamp("2023-06-01")
    raw["raw_customers"] = pd.concat([cu, hist], ignore_index=True)
    return clean, raw, pipe, notes


def f4d(seed):
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 44)
    cu = raw["raw_customers"]
    idx = cu.sample(n=25, random_state=int(rng.integers(0, 10**6))).index
    cu.loc[idx, "region"] = cu.loc[idx, "region"] + " "
    return clean, raw, pipe, notes


# ------------------------------------------------------------------ F5 values and units
def f5a(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 51))
    tx = raw["raw_transactions"]
    tx["amount_unit"] = "USD"
    m = tx.batch_id == b
    tx.loc[m, "amount"] = (tx.loc[m, "amount"] * 100).round(0)
    tx.loc[m, "amount_unit"] = "USD_CENTS"
    return clean, raw, pipe, notes


def f5b(seed):
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 52)
    b = _batch(rng)
    ctx, tx = clean["raw_transactions"], raw["raw_transactions"]
    idx = ctx[ctx.batch_id == b].sample(frac=0.25, random_state=int(rng.integers(0, 10**6))).index
    eur = [round(int(rng.integers(100, 4000)) * 0.04, 2) for _ in idx]
    tx.loc[idx, "amount"] = eur
    tx.loc[idx, "currency"] = "EUR"
    ctx.loc[idx, "amount"] = [round(e * 1.25, 2) for e in eur]
    raw["raw_fx_rates"] = pd.DataFrame({"currency": ["USD", "EUR", "GBP"],
                                        "rate_to_usd": [1.0, 1.25, 1.5],
                                        "as_of": [pd.Timestamp("2026-01-01")] * 3})
    return clean, raw, pipe, notes


def f5c(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 53))
    tx = raw["raw_transactions"]
    m = (tx.batch_id >= b) & (tx.status == "POSTED")
    tx.loc[m, "status"] = "SETTLED"
    notes.append(f"2026-01-{4 + b:02d} payments-source: status value POSTED renamed to SETTLED in the card feed; "
                 "meaning is unchanged.")
    return clean, raw, pipe, notes


def f5d(seed):
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 54))
    tx = raw["raw_transactions"]
    m = tx.batch_id == b
    tx["merchant_id"] = [f"M-{int(x):04d}" if mm else str(int(x)) for x, mm in zip(tx.merchant_id, m)]
    return clean, raw, pipe, notes


# ------------------------------------------------------------------ F6 escalation required
def f6a(seed):  # truncated delivery: data loss, needs re-delivery
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 61)
    tx = raw["raw_transactions"]
    last = tx[tx.batch_id == 14]
    drop = last.sample(frac=0.6, random_state=int(rng.integers(0, 10**6))).index
    raw["raw_transactions"] = tx.drop(index=drop).reset_index(drop=True)
    return clean, raw, pipe, notes


def f6b(seed):  # ambiguous magnitude jump for some merchants, no unit marker
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 62)
    b = _batch(rng)
    tx = raw["raw_transactions"]
    ms = rng.choice(tx.merchant_id.unique(), 3, replace=False)
    m = (tx.batch_id == b) & tx.merchant_id.isin(ms)
    tx.loc[m, "amount"] = (tx.loc[m, "amount"] * 100).round(2)
    return clean, raw, pipe, notes


def f6c(seed):  # personal data leaked into a dimension column
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 63)
    cu = raw["raw_customers"]
    idx = cu.sample(n=15, random_state=int(rng.integers(0, 10**6))).index
    cu.loc[idx, "region"] = [f"user{int(rng.integers(1000, 9999))}@examplemail.com" for _ in idx]
    return clean, raw, pipe, notes


def f6d(seed):  # upstream stopped sending a required column
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 64))
    tx = raw["raw_transactions"]
    tx["merchant_id"] = tx["merchant_id"].astype("Int64")
    tx.loc[tx.batch_id >= b, "merchant_id"] = pd.NA
    return clean, raw, pipe, notes


INCIDENTS = [
    Incident("F1a", "schema_drift", "amount column renamed", "fix", f1a),
    Incident("F1b", "schema_drift", "currency-formatted amount strings", "fix", f1b),
    Incident("F1c", "schema_drift", "epoch-millisecond timestamps", "fix", f1c),
    Incident("F1d", "schema_drift", "lower-case status values", "fix", f1d),
    Incident("F2a", "duplicates", "batch reloaded twice", "fix", f2a),
    Incident("F2b", "duplicates", "at-least-once duplicates", "fix", f2b),
    Incident("F2c", "duplicates", "corrected records resent", "fix", f2c),
    Incident("F2d", "duplicates", "duplicate dimension rows", "fix", f2d),
    Incident("F3a", "time", "UTC timestamps in one batch", "fix", f3a),
    Incident("F3b", "time", "late events dropped by filter", "fix", f3b),
    Incident("F3c", "time", "event date taken from ingest time", "fix", f3c),
    Incident("F3d", "time", "day-first timestamp strings", "fix", f3d),
    Incident("F4a", "keys", "leading zeros lost in key", "fix", f4a),
    Incident("F4b", "keys", "lower-case keys", "fix", f4b),
    Incident("F4c", "keys", "dimension history rows", "fix", f4c),
    Incident("F4d", "keys", "trailing spaces in dimension", "fix", f4d),
    Incident("F5a", "values", "amounts in cents", "fix", f5a),
    Incident("F5b", "values", "foreign-currency amounts", "fix", f5b),
    Incident("F5c", "values", "status value renamed", "fix", f5c),
    Incident("F5d", "values", "prefixed merchant ids", "fix", f5d),
    Incident("F6a", "escalate", "truncated delivery", "escalate", f6a),
    Incident("F6b", "escalate", "ambiguous magnitude jump", "escalate", f6b),
    Incident("F6c", "escalate", "personal data in dimension", "escalate", f6c),
    Incident("F6d", "escalate", "required column no longer sent", "escalate", f6d),
]

# ------------------------------------------------------------------ H: hard split
# Compound faults, decoys and look-alike escalations.
def h1(seed):  # compound: one batch has '$' amounts AND lower-case status
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 71))
    tx = raw["raw_transactions"]
    m = tx.batch_id == b
    tx["amount"] = [f"${a:,.2f}" if mm else f"{a:.2f}" for a, mm in zip(tx.amount, m)]
    tx.loc[m, "status"] = tx.loc[m, "status"].str.lower()
    return clean, raw, pipe, notes


def h2(seed):  # corrections resent in the same delivery; only record_version orders them
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 72)
    b = _batch(rng)
    ctx = clean["raw_transactions"]
    idx = ctx[ctx.batch_id == b].sample(frac=0.08, random_state=int(rng.integers(0, 10**6))).index
    tx = raw["raw_transactions"]
    tx["record_version"] = 1
    corr = tx.loc[idx].copy()
    new_amt = [round(a * float(rng.uniform(0.5, 1.5)), 2) for a in corr.amount]
    corr["amount"] = new_amt
    corr["record_version"] = 2
    ctx.loc[idx, "amount"] = new_amt
    out = pd.concat([tx, corr], ignore_index=True)
    raw["raw_transactions"] = out.sample(frac=1.0, random_state=int(rng.integers(0, 10**6))).reset_index(drop=True)
    notes.append(f"2026-01-{4 + b:02d} payments-source: amount corrections are now sent inside the regular daily "
                 "delivery; a corrected record repeats the txn_id with record_version incremented.")
    return clean, raw, pipe, notes


def h3(seed):  # partial collector rollout: only v2 rows are in UTC
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 73)
    b = _batch(rng)
    tx = raw["raw_transactions"]
    tx["collector"] = "legacy"
    m = (tx.batch_id >= b) & (rng.random(len(tx)) < 0.4)
    tx.loc[m, "txn_ts"] = tx.loc[m, "txn_ts"] + pd.Timedelta(hours=6)
    tx.loc[m, "collector"] = "v2"
    notes.append(f"2026-01-{3 + b:02d} ingestion: v2 card collector rolling out gradually alongside legacy. "
                 "v2 emits txn_ts in UTC; legacy emits America/Chicago local time.")
    return clean, raw, pipe, notes


def h4(seed):  # new CRM sends region codes; a mapping table exists
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 74)
    code = {"WEST": "01", "EAST": "02", "NORTH": "03", "SOUTH": "04"}
    cu = raw["raw_customers"]
    idx = cu.sample(frac=0.3, random_state=int(rng.integers(0, 10**6))).index
    cu.loc[idx, "region"] = [code[r] for r in cu.loc[idx, "region"]]
    raw["raw_region_map"] = pd.DataFrame({"region_code": list(code.values()), "region_name": list(code.keys())})
    notes.append("2026-01-15 crm: customers migrated to the new CRM carry a region code; "
                 "raw_region_map lists the codes.")
    return clean, raw, pipe, notes


def h5(seed):  # reversals now arrive as separate records; originals stay POSTED
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 75)
    b = _batch(rng)
    tx = raw["raw_transactions"]
    tx["orig_txn_id"] = pd.array([pd.NA] * len(tx), dtype="Int64")
    m = (tx.batch_id >= b) & (tx.status == "REVERSED")
    rev = tx[m].copy()
    tx.loc[m, "status"] = "POSTED"
    rev["orig_txn_id"] = rev["txn_id"].astype("Int64")
    rev["txn_id"] = np.arange(990001, 990001 + len(rev))
    rev["status"] = "REVERSAL"
    raw["raw_transactions"] = pd.concat([tx, rev], ignore_index=True)
    notes.append(f"2026-01-{4 + b:02d} payments-source: a reversal is now sent as a separate record with status "
                 "REVERSAL and orig_txn_id pointing to the original; the original record is no longer updated.")
    return clean, raw, pipe, notes


def h6(seed):  # duplicates with conflicting amounts, values still being recalculated
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 76)
    b = _batch(rng)
    tx = raw["raw_transactions"]
    dup = tx[tx.batch_id == b].sample(frac=0.06, random_state=int(rng.integers(0, 10**6))).copy()
    dup["amount"] = [round(a * float(rng.uniform(0.5, 1.5)), 2) for a in dup.amount]
    raw["raw_transactions"] = pd.concat([tx, dup], ignore_index=True).sort_values(["batch_id", "txn_id"]).reset_index(drop=True)
    notes.append(f"2026-01-{5 + b:02d} payments-source (PAY-77): part of the latest delivery was sent twice during an "
                 "amount recalculation; which copy carries the final amount is not yet known.")
    return clean, raw, pipe, notes


def h7(seed):  # amounts now net of fees; gross not recoverable from the evidence
    clean, raw, pipe, notes = _base(seed)
    rng = _rng(seed, 77)
    b = _batch(rng)
    tx = raw["raw_transactions"]
    mcc = dict(zip(raw["raw_merchants"].merchant_id, raw["raw_merchants"].mcc))
    fee = {k: float(rng.uniform(0.015, 0.03)) for k in sorted(set(mcc.values()))}
    m = tx.batch_id >= b
    tx.loc[m, "amount"] = [round(a * (1 - fee[mcc[mid]]), 2) for a, mid in zip(tx.loc[m, "amount"], tx.loc[m, "merchant_id"])]
    notes.append(f"2026-01-{4 + b:02d} payments-source: amount is now reported net of interchange fees; fee rates "
                 "vary by merchant category and are published separately by the card network.")
    return clean, raw, pipe, notes


def h8(seed):  # batch re-sent, and the re-sent copy uses epoch-millisecond timestamps
    clean, raw, pipe, notes = _base(seed)
    b = _batch(_rng(seed, 78))
    tx = raw["raw_transactions"]
    tx["txn_ts"] = [_iso(t) for t in tx.txn_ts]
    rep = clean["raw_transactions"][clean["raw_transactions"].batch_id == b].copy()
    rep["txn_ts"] = [str(int(pd.Timestamp(t).value // 1_000_000)) for t in rep.txn_ts]
    rep["ingest_ts"] = rep["ingest_ts"] + pd.Timedelta(hours=3)
    raw["raw_transactions"] = pd.concat([tx, rep], ignore_index=True)
    return clean, raw, pipe, notes


HARD = [
    Incident("H1", "hard", "two faults in one batch", "fix", h1, split="hard"),
    Incident("H2", "hard", "in-delivery corrections ordered by version", "fix", h2, split="hard"),
    Incident("H3", "hard", "partial UTC rollout by collector", "fix", h3, split="hard"),
    Incident("H4", "hard", "region codes with mapping table", "fix", h4, split="hard"),
    Incident("H5", "hard", "reversals as separate records", "fix", h5, split="hard",
             complaint="Finance reports that gold card totals are higher than the settlement file for the most "
                       "recent business days. No data quality monitor fired."),
    Incident("H6", "hard", "conflicting duplicates under recalculation", "escalate", h6, split="hard"),
    Incident("H7", "hard", "amounts now net of fees", "escalate", h7, split="hard",
             complaint="Finance reports that gold card totals are about 2 percent lower than the settlement file "
                       "for the most recent business days. No data quality monitor fired."),
    Incident("H8", "hard", "batch re-sent with a different timestamp format", "fix", h8, split="hard"),
]
INCIDENTS = INCIDENTS + HARD
BY_ID = {i.iid: i for i in INCIDENTS}
