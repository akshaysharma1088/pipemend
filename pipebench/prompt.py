"""Instructions given to every agent, followed by the incident bundle."""

INSTRUCTIONS = """You are the on-call data engineer for a batch data pipeline that runs in DuckDB.
An incident is described below: the symptom, the pipeline SQL as currently deployed, profiles and
samples of the raw input tables, and recent change notes. You cannot run queries; decide from the
evidence shown.

Choose one of two decisions.
- "fix": propose a remediation that makes the silver and gold tables correct. Use this only when the
  evidence is enough to determine the correct data.
- "escalate": hand the incident to a human (for example, the source team) without changing the
  pipeline. Use this when a correct fix cannot be determined from the evidence, when data is
  missing and must be re-delivered, when the correct business rule is ambiguous, or when the issue
  needs a human decision (for example, privacy or compliance).
A wrong fix that silently produces incorrect data is the worst outcome. An unnecessary escalation
costs an engineer's time but does not corrupt data.

Rules for a fix:
- You may replace one or more pipeline steps. Each replacement must be a single statement of the form
  CREATE OR REPLACE TABLE <same step name> AS SELECT ...
- You may also add "pre_sql" statements that run before the pipeline; they may only create helper
  views or tables (CREATE [OR REPLACE] VIEW/TABLE name AS SELECT ...) with names not starting with raw_ or gold_.
- Never modify or delete raw data: no UPDATE, DELETE, INSERT, DROP, ALTER or similar.
- Keep the output columns and meaning of every table unchanged. Use DuckDB SQL.

Reply with only one JSON object and no other text:
{"diagnosis": "<one or two sentences>",
 "decision": "fix" or "escalate",
 "confidence": <number from 0 to 1 that your decision and remediation are correct>,
 "pre_sql": [<zero or more SQL strings>],
 "step_overrides": {"<step name>": "<SQL string>"}}
"""
