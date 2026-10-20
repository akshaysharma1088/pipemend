"""Rule-based self-healing baseline (RBSH): a fixed playbook keyed on the error
or alert type, followed by the same verification gate the agents get. If the
playbook has no rule for a symptom, or the gate still fails, it escalates."""
from __future__ import annotations

from . import core
from .reference import silver

DEDUP = ("CREATE OR REPLACE VIEW tx_dedup AS SELECT * FROM raw_transactions "
         "QUALIFY row_number() OVER (PARTITION BY txn_id ORDER BY ingest_ts DESC) = 1")


def propose(case) -> dict:
    sym = case.error or " ".join(case.alerts)
    kw = {}
    pre = []
    over = {}
    if case.error:
        if "Conversion" in case.error and "amount" in case.error.lower() or "Could not convert string" in case.error and "$" in case.error:
            kw["amt"] = "CAST(regexp_replace(CAST(amount AS VARCHAR), '[^0-9.-]', '', 'g') AS DECIMAL(12,2))"
        elif "Conversion" in case.error:
            # quarantine rows that do not parse, a common production rule
            pre.append("CREATE OR REPLACE VIEW tx_q AS SELECT * FROM raw_transactions "
                       "WHERE TRY_CAST(txn_ts AS TIMESTAMP) IS NOT NULL AND TRY_CAST(merchant_id AS INTEGER) IS NOT NULL")
            kw["src"] = "tx_q"
        else:
            return {"decision": "escalate", "confidence": 1.0, "rule": "no rule for error"}
    else:
        handled = False
        if "DUPLICATE_KEYS" in sym:
            pre.append(DEDUP)
            kw["src"] = "tx_dedup"
            handled = True
        if "RECONCILIATION" in sym:
            over["silver_customers"] = ("CREATE OR REPLACE TABLE silver_customers AS SELECT customer_id, any_value(upper(trim(region))) AS region "
                                        "FROM raw_customers GROUP BY customer_id")
            over["silver_merchants"] = ("CREATE OR REPLACE TABLE silver_merchants AS SELECT CAST(merchant_id AS INTEGER) AS merchant_id, "
                                        "any_value(mcc) AS mcc FROM raw_merchants GROUP BY 1")
            handled = True
        if "DOMAIN_CHECK" in sym:
            over["silver_customers"] = ("CREATE OR REPLACE TABLE silver_customers AS SELECT customer_id, upper(trim(region)) AS region "
                                        "FROM raw_customers")
            handled = True
        if "NULL_VALUES" in sym:
            kw["where"] = "status = 'POSTED' AND customer_id IS NOT NULL AND merchant_id IS NOT NULL AND amount IS NOT NULL"
            handled = True
        if not handled:
            return {"decision": "escalate", "confidence": 1.0, "rule": "no rule for alert"}
    if kw:
        over["silver_transactions"] = silver(**kw)
    return {"decision": "fix", "confidence": 1.0, "pre_sql": pre, "step_overrides": over}


def run(case) -> dict:
    """Apply the playbook, then gate it: escalate if monitors still alert."""
    resp = propose(case)
    if resp["decision"] == "escalate":
        r = case.evaluate(resp)
        r["policy_outcome"] = r["outcome"]
        return r
    r = case.evaluate(resp)
    if r.get("gate_alerts"):
        r["policy_outcome"] = "correct_escalation" if case.inc.expected == "escalate" else "unnecessary_escalation"
        r["gated"] = True
    else:
        r["policy_outcome"] = r["outcome"]
    return r
